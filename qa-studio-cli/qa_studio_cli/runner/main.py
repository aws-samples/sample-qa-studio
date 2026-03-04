"""Main runner execution logic.

Uses unified ApiClient with TokenResolver instead of Settings + OAuthClient.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from qa_studio_cli.api.client import ApiClient
from qa_studio_cli.api.executions import ExecutionAPI
from qa_studio_cli.api.test_suites import TestSuiteAPI
from qa_studio_cli.api.usecases import UseCaseAPI
from qa_studio_cli.auth.resolver import TokenResolver
from qa_studio_cli.config.manager import load_config
from qa_studio_cli.models.errors import ExecutionError
from qa_studio_cli.runner.artifact_uploader import ArtifactUploader
from qa_studio_cli.runner.engine import ExecutionEngine
from qa_studio_cli.runner.output import SummaryFormatter
from qa_studio_cli.runner.suite_log_capture import SuiteLogCapture
from qa_studio_cli.utils.errors import sanitize_error_message
from qa_studio_cli.utils.url import apply_base_url_override
from qa_studio_cli.utils.variables import merge_variables

logger = logging.getLogger(__name__)


def _build_api_client(
    token_file: Optional[str] = None,
) -> ApiClient:
    """Build an ApiClient using the TokenResolver chain."""
    config = load_config()
    resolver = TokenResolver(token_file=token_file, config=config)
    return ApiClient(base_url=config.api_url, token_provider=resolver.get_token)


def _validate_aws_session() -> None:
    """Validate that a working AWS session exists."""
    import boto3  # lazy import — runner extra

    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        logger.info("AWS session valid - Account: %s, ARN: %s", identity["Account"], identity["Arn"])
    except Exception as e:
        raise ExecutionError(
            "No valid AWS session found. Nova Act requires AWS credentials "
            "for Bedrock access. Please configure AWS credentials via environment "
            "variables (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY), AWS SSO, "
            f"or an IAM role. Error: {sanitize_error_message(str(e))}"
        )


def determine_exit_code(results: List[Dict[str, Any]]) -> int:
    """Determine exit code based on execution results.

    Returns:
        0: All tests passed, 1: One or more failed, 2: Runner error (no results)
    """
    if not results:
        return 2
    for r in results:
        if r["status"] == "failed":
            return 1
    return 0


def run_usecase(
    usecase_id: str,
    local_only: bool,
    token_file: Optional[str] = None,
    base_url: Optional[str] = None,
    variables: Optional[Dict[str, str]] = None,
    region: Optional[str] = None,
    model_id: Optional[str] = None,
    timeout: int = 3600,
    output_format: str = "json",
) -> None:
    """Execute a single use case (local-only or remote mode)."""
    try:
        logger.info("Loading configuration...")
        _validate_aws_session()

        api_client = _build_api_client(token_file=token_file)
        usecase_api = UseCaseAPI(api_client)

        if local_only:
            _run_usecase_local(
                usecase_id=usecase_id,
                usecase_api=usecase_api,
                base_url=base_url,
                variables=variables or {},
                region=region,
                model_id=model_id,
                output_format=output_format,
            )
        else:
            _run_usecase_remote(
                usecase_id=usecase_id,
                usecase_api=usecase_api,
                api_client=api_client,
                base_url=base_url,
                variables=variables or {},
                region=region,
                model_id=model_id,
                output_format=output_format,
            )
    except Exception as e:
        sanitized_error = sanitize_error_message(str(e))
        logger.error("Runner failed: %s", sanitized_error, exc_info=True)
        sys.exit(2)


def _run_usecase_local(
    usecase_id: str,
    usecase_api: UseCaseAPI,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    output_format: str = "json",
) -> None:
    """Local-only execution path: fetch data, execute locally, print result."""
    logger.info("Fetching use case: %s", usecase_id)
    usecase = usecase_api.get_usecase(usecase_id)
    steps = usecase_api.get_steps(usecase_id)
    api_variables = usecase_api.get_variables(usecase_id)
    secrets = usecase_api.get_secrets(usecase_id)

    usecase_name = usecase.get("name", usecase_id)
    starting_url = usecase.get("starting_url", "")

    if base_url:
        starting_url = apply_base_url_override(starting_url, base_url)

    merged_variables = merge_variables(api_variables, variables)
    effective_region = region or usecase.get("executing_region", "us-east-1")
    effective_model = model_id or usecase.get("model_id", "nova-act-v1.0")

    logger.info("Executing use case locally: %s", usecase_name)
    engine = ExecutionEngine()
    result = engine.execute_usecase_local(
        usecase_id=usecase_id,
        usecase_name=usecase_name,
        starting_url=starting_url,
        steps=steps,
        variables=merged_variables,
        secrets=secrets,
        region=effective_region,
        model_id=effective_model,
    )

    if output_format == "human":
        print("\n" + SummaryFormatter.format_usecase(result) + "\n")
    else:
        print(json.dumps(result, indent=2))

    exit_code = 0 if result.get("status") == "success" else 1
    logger.info("Local execution completed with exit code: %d", exit_code)
    sys.exit(exit_code)


def _run_usecase_remote(
    usecase_id: str,
    usecase_api: UseCaseAPI,
    api_client: ApiClient,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    output_format: str = "json",
) -> None:
    """Remote execution path: create execution record, execute with tracking."""
    from qa_studio_cli.models.execution import RemoteExecutionResult

    logger.info("Creating execution record for use case: %s", usecase_id)
    execution_response = usecase_api.create_execution(
        usecase_id=usecase_id,
        trigger_type="ci_runner",
        base_url=base_url,
        variables=variables if variables else None,
        region=region,
        model_id=model_id,
    )

    execution_id = execution_response.get("executionId") or execution_response.get("execution_id")
    logger.info("Execution created: %s", execution_id)

    execution_api = ExecutionAPI(api_client)
    execution_details = asyncio.run(
        execution_api.get_execution(usecase_id, execution_id)
    )

    execution = {
        "execution_id": execution_id,
        "usecase_id": usecase_id,
        "usecase_name": execution_details.get("usecase_name", usecase_id),
    }

    engine = ExecutionEngine(execution_api=execution_api, suite_execution_id=None)
    result = asyncio.run(engine.execute_usecase(execution))

    remote_result = RemoteExecutionResult(
        status=result.get("status", "failed"),
        usecase_id=usecase_id,
        usecase_name=result.get("usecase_name", usecase_id),
        execution_id=execution_id,
        duration=result.get("duration", 0),
        steps=[],
    )

    output = remote_result.model_dump(by_alias=True)
    if output_format == "human":
        print("\n" + SummaryFormatter.format_usecase(output) + "\n")
    else:
        print(json.dumps(output, indent=2))

    exit_code = 0 if result.get("status") == "success" else 1
    logger.info("Remote execution completed with exit code: %d", exit_code)
    sys.exit(exit_code)


def run_runner(
    suite_id: str,
    local_only: bool = False,
    base_url: Optional[str] = None,
    variables: Optional[Dict[str, str]] = None,
    region: Optional[str] = None,
    model_id: Optional[str] = None,
    timeout: int = 3600,
    keep_artifacts: bool = False,
    token_file: Optional[str] = None,
    output_format: str = "json",
) -> None:
    """Main runner execution logic for suite mode."""
    variables = variables or {}

    try:
        logger.info("Loading configuration...")
        _validate_aws_session()

        api_client = _build_api_client(token_file=token_file)
        test_suite_api = TestSuiteAPI(api_client)
        usecase_api = UseCaseAPI(api_client)

        logger.info("Fetching test suite: %s", suite_id)
        suite = test_suite_api.get_suite(suite_id)
        logger.info("Found test suite: %s", suite["name"])

        if local_only:
            _run_suite_local(
                suite=suite,
                suite_id=suite_id,
                test_suite_api=test_suite_api,
                usecase_api=usecase_api,
                base_url=base_url,
                variables=variables,
                region=region,
                model_id=model_id,
                output_format=output_format,
            )
        else:
            _run_suite_remote(
                suite=suite,
                suite_id=suite_id,
                test_suite_api=test_suite_api,
                api_client=api_client,
                base_url=base_url,
                variables=variables,
                region=region,
                model_id=model_id,
                timeout=timeout,
                keep_artifacts=keep_artifacts,
            )
    except Exception as e:
        sanitized_error = sanitize_error_message(str(e))
        logger.error("Runner failed: %s", sanitized_error, exc_info=True)
        sys.exit(2)


def _run_suite_local(
    suite: Dict[str, Any],
    suite_id: str,
    test_suite_api: TestSuiteAPI,
    usecase_api: UseCaseAPI,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    output_format: str = "json",
) -> None:
    """Local-only suite execution."""
    start_time = datetime.utcnow()

    logger.info("Fetching usecases for suite: %s", suite_id)
    suite_usecases = test_suite_api.list_usecases(suite_id)
    logger.info("Found %d usecases in suite", len(suite_usecases))

    if not suite_usecases:
        logger.warning("Suite has no usecases — nothing to execute")
        print("Suite has no usecases to execute.")
        sys.exit(0)

    engine = ExecutionEngine()
    results: List[Dict[str, Any]] = []

    for uc in suite_usecases:
        uc_id = uc.get("usecaseId", uc.get("usecase_id", ""))
        uc_name = uc.get("usecaseName", uc.get("usecase_name", uc_id))

        logger.info("Executing usecase locally: %s (%s)", uc_name, uc_id)

        usecase = usecase_api.get_usecase(uc_id)
        steps = usecase_api.get_steps(uc_id)
        api_variables = usecase_api.get_variables(uc_id)
        secrets = usecase_api.get_secrets(uc_id)

        starting_url = usecase.get("starting_url", "")
        if base_url:
            starting_url = apply_base_url_override(starting_url, base_url)

        merged_variables = merge_variables(api_variables, variables)
        effective_region = region or usecase.get("executing_region", "us-east-1")
        effective_model = model_id or usecase.get("model_id", "nova-act-v1.0")

        result = engine.execute_usecase_local(
            usecase_id=uc_id,
            usecase_name=uc_name,
            starting_url=starting_url,
            steps=steps,
            variables=merged_variables,
            secrets=secrets,
            region=effective_region,
            model_id=effective_model,
        )
        results.append(result)

    end_time = datetime.utcnow()

    summary_results = _local_results_to_summary(results)
    if output_format == "human":
        summary = SummaryFormatter.format_table(
            suite_name=suite["name"],
            suite_execution_id="local",
            results=summary_results,
            start_time=start_time,
            end_time=end_time,
        )
        print("\n" + summary + "\n")
    else:
        print(json.dumps(results, indent=2))

    exit_code = determine_exit_code(summary_results)
    logger.info("Local suite execution completed with exit code: %d", exit_code)
    sys.exit(exit_code)


def _local_results_to_summary(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert local execution results to the format expected by SummaryFormatter."""
    summary = []
    for r in results:
        summary.append({
            "usecase_name": r.get("usecaseName", r.get("usecase_name", "Unknown")),
            "status": r.get("status", "failed"),
            "duration": r.get("duration", 0),
        })
    return summary


def _run_suite_remote(
    suite: Dict[str, Any],
    suite_id: str,
    test_suite_api: TestSuiteAPI,
    api_client: ApiClient,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    timeout: int = 3600,
    keep_artifacts: bool = False,
) -> None:
    """Remote suite execution: create execution records, run in parallel, upload artifacts."""
    logger.info("Creating execution records...")
    execution_response = test_suite_api.execute_suite(
        suite_id=suite_id,
        base_url=base_url,
        variables=variables,
        region=region,
        model_id=model_id,
    )

    suite_execution_id = execution_response["suite_execution_id"]
    execution_ids = execution_response["execution_ids"]

    logger.info("Suite execution created: %s", suite_execution_id)
    logger.info("Created %d execution records", len(execution_ids))

    start_time = datetime.utcnow()

    execution_api = ExecutionAPI(api_client)
    execution_engine = ExecutionEngine(
        execution_api, suite_execution_id, keep_artifacts=keep_artifacts,
    )

    suite_log_capture = SuiteLogCapture(suite_execution_id)
    suite_log_capture.start()

    try:
        logger.info("Executing use cases in parallel...")
        results = asyncio.run(execution_engine.execute_all(execution_ids))
    except Exception:
        suite_log_capture.stop()
        raise

    end_time = datetime.utcnow()

    logger.info("Updating suite execution status...")
    try:
        if not results:
            suite_status = "failed"
        elif all(r["status"] == "success" for r in results):
            suite_status = "completed"
        elif any(r["status"] == "success" for r in results):
            suite_status = "partial"
        else:
            suite_status = "failed"

        asyncio.run(execution_api.update_suite_status(
            suite_id=suite_id,
            suite_execution_id=suite_execution_id,
            status=suite_status,
        ))
        logger.info("Suite execution status updated to: %s", suite_status)
    except Exception as e:
        logger.warning("Failed to update suite execution status: %s", e)

    logger.info("Generating execution summary...")
    summary = SummaryFormatter.format_table(
        suite_name=suite["name"],
        suite_execution_id=suite_execution_id,
        results=results,
        start_time=start_time,
        end_time=end_time,
    )
    print("\n" + summary + "\n")

    exit_code = determine_exit_code(results)
    logger.info("Execution completed with exit code: %d", exit_code)

    suite_log_path = suite_log_capture.stop()
    if suite_log_path:
        try:
            artifact_uploader = ArtifactUploader(api_client)
            asyncio.run(artifact_uploader.upload_suite_artifacts(
                suite_id=suite_id,
                suite_execution_id=suite_execution_id,
                artifacts={"logs": suite_log_path},
            ))
        except Exception as e:
            logger.warning("Failed to upload suite logs: %s", e)

    sys.exit(exit_code)
