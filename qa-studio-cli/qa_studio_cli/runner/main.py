"""Main runner execution logic.

Uses unified ApiClient with TokenResolver instead of Settings + OAuthClient.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import click

from qa_studio_cli.api.applications import ApplicationsAPI
from qa_studio_cli.api.client import ApiClient, build_api_client
from qa_studio_cli.api.executions import ExecutionAPI
from qa_studio_cli.api.test_suites import TestSuiteAPI
from qa_studio_cli.api.usecases import UseCaseAPI
from qa_studio_cli.auth.resolver import TokenResolver
from qa_studio_cli.config.manager import load_config
from qa_studio_cli.models.errors import ExecutionError
from qa_studio_cli.runner.artifact_uploader import ArtifactUploader
from qa_studio_cli.runner.browser import BrowserSelection, ElectronLaunchConfig
from qa_studio_cli.runner.dataset_file import DatasetEntry, resolve_repeat_datasets
from qa_studio_cli.runner.dataset_ref import (
    DatasetFetcher,
    application_dataset_fetcher,
    resolve_usecase_dataset_refs,
)
from qa_studio_cli.runner.deadline import RunDeadline, run_bounded
from qa_studio_cli.runner.engine import ExecutionEngine
from qa_studio_cli.runner import progress
from qa_studio_cli.runner.output import SummaryFormatter
from qa_studio_cli.runner.repeat_expansion import expand_repeat_steps
from qa_studio_cli.runner.suite_log_capture import SuiteLogCapture
from qa_studio_cli.utils.errors import sanitize_error_message
from qa_studio_cli.utils.url import apply_base_url_override
from qa_studio_cli.utils.variables import merge_variables

logger = logging.getLogger(__name__)


def _build_api_client(
    token_file: Optional[str] = None,
) -> ApiClient:
    """Thin wrapper around the shared builder to preserve the runner's
    historical function name and keep call sites unchanged."""
    return build_api_client(token_file=token_file)


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
        0: All tests passed, 1: One or more not successful (failed or
        skipped), 2: Runner error (no results)
    """
    if not results:
        return 2
    for r in results:
        if r["status"] != "success":
            return 1
    return 0


def _apply_timeout(exit_code: int, deadline: Optional[RunDeadline]) -> int:
    """The deadline's exit code when ``--timeout`` or SIGTERM cut an
    unsuccessful run short (3 for a timeout, 143 for a termination).

    A run that passed is a pass even if it finished just after the deadline.
    A termination was already announced when the signal arrived.
    """
    if exit_code != 0 and deadline is not None and deadline.expired():
        if not deadline.terminated:
            progress.run_timed_out(deadline.message)
        return deadline.exit_code
    return exit_code


def _build_electron_launch(
    app_path: Optional[str],
    app_args: Optional[List[str]],
    app_user_data_dir: Optional[str],
) -> Optional[ElectronLaunchConfig]:
    """Translate the ``--app-path`` family of flags into an engine config.

    Returns ``None`` when no app path was given — web and mobile runs
    never need it (mobile consumes ``app_path`` through ``mobile_config``
    instead).  Electron usecases then fail inside the engine with a
    message naming ``--app-path``.
    """
    if not app_path:
        return None
    return ElectronLaunchConfig(
        app_path=app_path,
        app_args=tuple(app_args or ()),
        user_data_dir=app_user_data_dir,
    )

def _build_browser_selection(
    browser: str,
    cdp_endpoint_url: Optional[str],
    cdp_headers_file: Optional[str],
    local_browser: str,
    headful: bool,
) -> BrowserSelection:
    """Translate the ``--browser`` family of flags into an engine config."""
    return BrowserSelection(
        mode=browser,
        cdp_endpoint_url=cdp_endpoint_url,
        cdp_headers_file=cdp_headers_file,
        local_browser=local_browser,
        headless=False if headful else None,
    )


def run_usecase(
    usecase_ids: List[str],
    local_only: bool,
    fail_fast: bool = False,
    token_file: Optional[str] = None,
    base_url: Optional[str] = None,
    variables: Optional[Dict[str, str]] = None,
    region: Optional[str] = None,
    model_id: Optional[str] = None,
    timeout: Optional[int] = None,
    output_format: str = "json",
    device_arn: Optional[str] = None,
    app_path: Optional[str] = None,
    execution_id: Optional[str] = None,
    browser: str = "local",
    cdp_endpoint_url: Optional[str] = None,
    cdp_headers_file: Optional[str] = None,
    local_browser: str = "chromium",
    headful: bool = False,
    app_args: Optional[List[str]] = None,
    app_user_data_dir: Optional[str] = None,
    repeat_dataset_files: Optional[List[DatasetEntry]] = None,
) -> None:
    """Execute one or more use cases sequentially (local-only or remote).

    Every definition is fetched before anything runs, so an unknown ID
    exits with code 2 without launching a browser.  Each use case then
    gets its own engine (and, in remote mode, its own execution record).
    A use case that fails — or raises — is recorded as ``failed`` and the
    loop continues unless ``fail_fast`` is set, in which case the
    remaining use cases are reported as ``skipped``.

    With exactly one ID the output is the bare result, byte-identical to
    the historical single-use-case behaviour (the ECS worker and CI
    pipelines parse it).  With several IDs a :class:`MultiRunSummary` is
    printed instead.

    When ``execution_id`` is provided, the remote path attaches to the
    pre-created execution record instead of creating a new one.  It is
    only honoured for a single ID; the ``local_only`` path ignores it —
    local runs never touch the remote state machine.

    ``browser`` selects the BrowserProvisioner strategy.  ``local`` and
    ``cdp-external`` are supported on the local-only path; the remote
    path additionally supports ``agentcore`` which provisions a remote
    browser via Bedrock AgentCore (requires ``qa-studio[agentcore]``).

    ``app_path`` is shared by two platforms: mobile usecases upload it to
    Device Farm, electron usecases launch it (together with ``app_args``
    and ``app_user_data_dir``).  One value applies to every use case.

    ``repeat_dataset_files`` are the parsed ``--dataset-file`` entries
    ``(label|None, {"columns", "rows"})``; they replace the stored rows of
    the matching repeat step for this run (remote: sent to the API; local:
    applied by the local expansion).  Like ``app_path`` they apply to
    every use case given.

    ``timeout`` (seconds, ``None`` = no limit) bounds the whole run — see
    :mod:`qa_studio_cli.runner.deadline`.  Use cases not started before it
    expires are reported as ``skipped``; the exit code is then 3.  SIGTERM
    stops the run the same way (exit code 143, or 3 when the parent reports a
    timeout — see :mod:`qa_studio_cli.runner.termination`).
    """
    deadline = RunDeadline.start(timeout)
    run_bounded(deadline, lambda: _run_usecases(
        usecase_ids=usecase_ids, local_only=local_only, fail_fast=fail_fast,
        token_file=token_file, base_url=base_url, variables=variables,
        region=region, model_id=model_id, output_format=output_format,
        device_arn=device_arn, app_path=app_path, execution_id=execution_id,
        browser=browser, cdp_endpoint_url=cdp_endpoint_url,
        cdp_headers_file=cdp_headers_file, local_browser=local_browser,
        headful=headful, app_args=app_args, app_user_data_dir=app_user_data_dir,
        repeat_dataset_files=repeat_dataset_files, deadline=deadline,
    ))


def _run_usecases(
    usecase_ids: List[str],
    local_only: bool,
    fail_fast: bool,
    token_file: Optional[str],
    base_url: Optional[str],
    variables: Optional[Dict[str, str]],
    region: Optional[str],
    model_id: Optional[str],
    output_format: str,
    device_arn: Optional[str],
    app_path: Optional[str],
    execution_id: Optional[str],
    browser: str,
    cdp_endpoint_url: Optional[str],
    cdp_headers_file: Optional[str],
    local_browser: str,
    headful: bool,
    app_args: Optional[List[str]],
    app_user_data_dir: Optional[str],
    repeat_dataset_files: Optional[List[DatasetEntry]],
    deadline: Optional[RunDeadline],
) -> None:
    """Body of :func:`run_usecase` (runs under its ``--timeout``)."""
    from qa_studio_cli.models.execution import MultiRunEntry, MultiRunSummary

    try:
        logger.info("Loading configuration...")
        _validate_aws_session()

        api_client = _build_api_client(token_file=token_file)
        usecase_api = UseCaseAPI(api_client)
        electron_launch = _build_electron_launch(app_path, app_args, app_user_data_dir)

        usecases: Dict[str, Dict[str, Any]] = {}
        for uid in usecase_ids:
            logger.info("Fetching use case: %s", uid)
            usecases[uid] = usecase_api.get_usecase(uid)
    except Exception as e:
        sanitized_error = sanitize_error_message(str(e))
        logger.error("Runner failed: %s", sanitized_error, exc_info=True)
        sys.exit(2)

    if execution_id and local_only:
        logger.warning("--execution-id is ignored in --local-only mode")
    if execution_id and len(usecase_ids) > 1:
        logger.warning("--execution-id is ignored when more than one use case is given")
        execution_id = None

    entries: List[MultiRunEntry] = []
    last_result: Dict[str, Any] = {}
    stop = False
    for uid in usecase_ids:
        name = usecases[uid].get("name", uid)
        if stop:
            logger.info("Skipping use case %s (--fail-fast)", uid)
            entries.append(MultiRunEntry(usecase_id=uid, usecase_name=name, status="skipped"))
            continue
        if deadline is not None and deadline.expired():
            logger.info("Skipping use case %s (--timeout)", uid)
            entries.append(MultiRunEntry(usecase_id=uid, usecase_name=name, status="skipped",
                                         error=deadline.message))
            continue

        try:
            if local_only:
                result = _execute_usecase_local(
                    usecase_id=uid,
                    usecase=usecases[uid],
                    usecase_api=usecase_api,
                    base_url=base_url,
                    variables=variables or {},
                    region=region,
                    model_id=model_id,
                    device_arn=device_arn,
                    app_path=app_path,
                    browser=browser,
                    cdp_endpoint_url=cdp_endpoint_url,
                    cdp_headers_file=cdp_headers_file,
                    local_browser=local_browser,
                    headful=headful,
                    electron_launch=electron_launch,
                    repeat_dataset_files=repeat_dataset_files,
                    deadline=deadline,
                )
            else:
                result = _execute_usecase_remote(
                    usecase_id=uid,
                    usecase_api=usecase_api,
                    api_client=api_client,
                    base_url=base_url,
                    variables=variables or {},
                    region=region,
                    model_id=model_id,
                    execution_id=execution_id,
                    browser=browser,
                    cdp_endpoint_url=cdp_endpoint_url,
                    cdp_headers_file=cdp_headers_file,
                    local_browser=local_browser,
                    headful=headful,
                    electron_launch=electron_launch,
                    repeat_dataset_files=repeat_dataset_files,
                    usecase_name=name,
                    deadline=deadline,
                )
        except Exception as e:
            sanitized_error = sanitize_error_message(str(e))
            logger.error("Use case %s failed: %s", uid, sanitized_error, exc_info=True)
            if len(usecase_ids) == 1:
                # Historical single-ID contract: an executor error is a
                # runner error (exit 2), not a test failure.
                sys.exit(2)
            result = {"status": "failed", "usecaseId": uid, "usecaseName": name,
                      "duration": 0, "steps": [], "artifacts": {}, "error": sanitized_error}

        last_result = result
        if output_format == "human":
            print("\n" + SummaryFormatter.format_usecase(result) + "\n")
        entries.append(MultiRunEntry(
            usecase_id=uid,
            usecase_name=name,
            status="success" if result.get("status") == "success" else "failed",
            execution_id=result.get("executionId"),
            duration=result.get("duration", 0) or 0,
            error=result.get("error"),
        ))
        if fail_fast and entries[-1].status != "success":
            stop = True

    if len(usecase_ids) == 1 and last_result:
        if output_format != "human":
            print(json.dumps(last_result, indent=2))
        exit_code = 0 if last_result.get("status") == "success" else 1
    else:
        summary = MultiRunSummary.from_results(entries)
        if output_format == "human":
            # click.echo strips the ANSI colours when stdout is not a TTY.
            click.echo("\n" + SummaryFormatter.format_multi_summary(summary) + "\n")
        else:
            print(json.dumps(summary.model_dump(by_alias=True), indent=2))
        exit_code = determine_exit_code([e.model_dump() for e in entries])

    exit_code = _apply_timeout(exit_code, deadline)
    logger.info("Execution completed with exit code: %d", exit_code)
    sys.exit(exit_code)


def _execute_usecase_local(
    usecase_id: str,
    usecase: Dict[str, Any],
    usecase_api: UseCaseAPI,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    device_arn: Optional[str] = None,
    app_path: Optional[str] = None,
    browser: str = "local",
    cdp_endpoint_url: Optional[str] = None,
    cdp_headers_file: Optional[str] = None,
    local_browser: str = "chromium",
    headful: bool = False,
    electron_launch: Optional[ElectronLaunchConfig] = None,
    repeat_dataset_files: Optional[List[DatasetEntry]] = None,
    show_test_name_on_steps: bool = False,
    deadline: Optional[RunDeadline] = None,
    dataset_fetcher: Optional[DatasetFetcher] = None,
) -> Dict[str, Any]:
    """Local-only execution of one use case; returns the engine result.

    ``usecase`` is the already-fetched definition — this function fetches
    only steps, variables, secrets and (for repeat steps with a
    ``dataset_id``) the referenced application datasets.  It neither prints
    nor exits so callers can run several use cases and summarise afterwards.

    ``repeat_dataset_files`` (``--dataset-file``) replace the stored rows of
    the labelled repeat step(s) before expansion — after dataset references
    were resolved, so the file wins over the application dataset.

    ``dataset_fetcher`` overrides how referenced datasets are read (tests);
    by default they come from ``GET /applications/{app}/datasets/{id}`` for
    ``usecase["application_id"]``, which needs ``api/applications.read``.

    ``show_test_name_on_steps`` makes the engine prefix progress step lines
    with the test name (suite runs).
    """
    # --browser=agentcore is only valid on the remote path (needs the
    # live-view endpoint).  Reject it here with a clear error.
    if browser == "agentcore":
        raise RuntimeError(
            "--browser=agentcore is not supported with --local-only; "
            "use --browser=local (default) or --browser=cdp-external",
        )
    # Local-only runs read step *definitions*; resolve application dataset
    # references, then unroll repeat steps here so the engine sees the same
    # flat list the API produces in remote mode.  A missing dataset raises
    # RuntimeError and a bad repeat RepeatExpansionError before any browser
    # starts (exit 2).
    step_definitions = usecase_api.get_steps(usecase_id)
    application_id = usecase.get("application_id")
    if dataset_fetcher is None:
        dataset_fetcher = application_dataset_fetcher(ApplicationsAPI(usecase_api.client), application_id)
    step_definitions = resolve_usecase_dataset_refs(step_definitions, application_id, dataset_fetcher)
    repeat_datasets = resolve_repeat_datasets(repeat_dataset_files or [], step_definitions)
    steps = expand_repeat_steps(step_definitions, repeat_datasets)
    api_variables = usecase_api.get_variables(usecase_id)
    secrets = usecase_api.get_secrets(usecase_id)

    usecase_name = usecase.get("name", usecase_id)
    starting_url = usecase.get("starting_url", "")

    if base_url:
        starting_url = apply_base_url_override(starting_url, base_url)

    merged_variables = merge_variables(api_variables, variables)
    effective_model = model_id or usecase.get("model_id", "nova-act-v1.0")

    # Extract mobile config from usecase
    mobile_config = None
    test_platform = usecase.get("test_platform", "web")
    if test_platform == "mobile":
        mobile_config = {
            "platform": usecase.get("platform", ""),
            "app_package": usecase.get("app_package", ""),
            "app_activity": usecase.get("app_activity", ""),
            "bundle_id": usecase.get("bundle_id", ""),
            "device_arn": usecase.get("device_arn", ""),
            "app_binary_s3_path": usecase.get("app_binary_s3_path", ""),
            "app_arn": usecase.get("app_arn", ""),
            "device_farm_project_arn": usecase.get("device_farm_project_arn", ""),
        }
        logger.info("Mobile use case detected: platform=%s", mobile_config["platform"])

        # Apply CLI override for device ARN
        if device_arn:
            mobile_config["device_arn"] = device_arn
            logger.info("Using CLI device ARN override: %s", device_arn)
        if app_path:
            mobile_config["app_path"] = app_path
            logger.info("Using CLI app path: %s", app_path)

    if test_platform == "electron":
        logger.info("Electron use case detected")

    logger.info("Executing use case locally: %s", usecase_name)
    progress.test_started(usecase_name)
    engine = ExecutionEngine(
        browser_selection=_build_browser_selection(
            browser, cdp_endpoint_url, cdp_headers_file, local_browser, headful,
        ),
        electron_launch=electron_launch,
        show_test_name_on_steps=show_test_name_on_steps,
        deadline=deadline,
    )
    return engine.execute_usecase_local(
        usecase_id=usecase_id,
        usecase_name=usecase_name,
        starting_url=starting_url,
        steps=steps,
        variables=merged_variables,
        secrets=secrets,
        # --region wins; unset keeps boto's chain (AWS_REGION, then profile).
        region=region,
        model_id=effective_model,
        mobile_config=mobile_config,
        test_platform=test_platform,
        bundle_id=usecase.get("bundle_id") or None,
    )


def _execute_usecase_remote(
    usecase_id: str,
    usecase_api: UseCaseAPI,
    api_client: ApiClient,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    execution_id: Optional[str] = None,
    browser: str = "local",
    cdp_endpoint_url: Optional[str] = None,
    cdp_headers_file: Optional[str] = None,
    local_browser: str = "chromium",
    headful: bool = False,
    electron_launch: Optional[ElectronLaunchConfig] = None,
    repeat_dataset_files: Optional[List[DatasetEntry]] = None,
    usecase_name: Optional[str] = None,
    deadline: Optional[RunDeadline] = None,
) -> Dict[str, Any]:
    """Remote execution of one use case; returns the dumped result.

    Creates an execution record and runs the engine with status tracking.
    When ``execution_id`` is supplied, the creation step is skipped and the
    runner attaches to the supplied pre-created record instead.  This is
    the path the cloud worker takes: the web API creates the execution
    record before the ECS task starts, and the task receives the id via
    env var.

    ``repeat_dataset_files`` travel in the ``POST /usecase/{id}/execute``
    body as ``repeat_datasets``; the Lambda unrolls them instead of the
    stored rows.  Resolving the label needs the step definitions, so they
    are fetched only when a dataset file was given.

    ``usecase_name`` is the name from the already-fetched definition.  Only
    suite-created execution records carry ``usecase_name``; a single-use-case
    record does not, so without this the progress line and the result would
    show the use case id instead of the name.

    Neither prints nor exits — see ``_execute_usecase_local``.
    """
    from qa_studio_cli.models.execution import RemoteExecutionResult

    if execution_id:
        if repeat_dataset_files:
            raise RuntimeError(
                "--dataset-file cannot be combined with --execution-id: the "
                "execution's steps were already created by the server",
            )
        logger.info(
            "Attaching to pre-created execution: %s (usecase %s)",
            execution_id, usecase_id,
        )
    else:
        repeat_datasets = None
        if repeat_dataset_files:
            repeat_datasets = resolve_repeat_datasets(
                repeat_dataset_files, usecase_api.get_steps(usecase_id),
            )
        logger.info("Creating execution record for use case: %s", usecase_id)
        execution_response = usecase_api.create_execution(
            usecase_id=usecase_id,
            trigger_type="ci_runner",
            base_url=base_url,
            variables=variables if variables else None,
            region=region,
            model_id=model_id,
            repeat_datasets=repeat_datasets,
        )
        execution_id = (
            execution_response.get("executionId")
            or execution_response.get("execution_id")
        )
        logger.info("Execution created: %s", execution_id)

    execution_api = ExecutionAPI(api_client)
    execution_details = asyncio.run(
        execution_api.get_execution(usecase_id, execution_id)
    )

    execution = {
        "execution_id": execution_id,
        "usecase_id": usecase_id,
        "usecase_name": usecase_name or execution_details.get("usecase_name") or usecase_id,
    }

    engine = ExecutionEngine(
        execution_api=execution_api,
        suite_execution_id=None,
        browser_selection=_build_browser_selection(
            browser, cdp_endpoint_url, cdp_headers_file, local_browser, headful,
        ),
        electron_launch=electron_launch,
        show_test_name_on_steps=False,
        deadline=deadline,
    )
    result = asyncio.run(engine.execute_usecase(execution))

    remote_result = RemoteExecutionResult(
        status=result.get("status", "failed"),
        usecase_id=usecase_id,
        usecase_name=result.get("usecase_name") or execution["usecase_name"],
        execution_id=execution_id,
        duration=result.get("duration", 0),
        steps=[],
    )
    return remote_result.model_dump(by_alias=True)

def run_runner(
    suite_id: str,
    local_only: bool = False,
    base_url: Optional[str] = None,
    variables: Optional[Dict[str, str]] = None,
    region: Optional[str] = None,
    model_id: Optional[str] = None,
    timeout: Optional[int] = None,
    keep_artifacts: bool = False,
    token_file: Optional[str] = None,
    output_format: str = "json",
    local_browser: str = "chromium",
    headful: bool = False,
    app_path: Optional[str] = None,
    app_args: Optional[List[str]] = None,
    app_user_data_dir: Optional[str] = None,
) -> None:
    """Main runner execution logic for suite mode.

    One ``--app-path`` applies to every electron usecase in the suite;
    web usecases in a mixed suite ignore it.  ``timeout`` bounds the whole
    run as in :func:`run_usecase`.
    """
    deadline = RunDeadline.start(timeout)
    run_bounded(deadline, lambda: _run_suite(
        suite_id=suite_id, local_only=local_only, base_url=base_url,
        variables=variables, region=region, model_id=model_id,
        keep_artifacts=keep_artifacts, token_file=token_file,
        output_format=output_format, local_browser=local_browser,
        headful=headful, app_path=app_path, app_args=app_args,
        app_user_data_dir=app_user_data_dir, deadline=deadline,
    ))


def _run_suite(
    suite_id: str,
    local_only: bool,
    base_url: Optional[str],
    variables: Optional[Dict[str, str]],
    region: Optional[str],
    model_id: Optional[str],
    keep_artifacts: bool,
    token_file: Optional[str],
    output_format: str,
    local_browser: str,
    headful: bool,
    app_path: Optional[str],
    app_args: Optional[List[str]],
    app_user_data_dir: Optional[str],
    deadline: Optional[RunDeadline],
) -> None:
    """Body of :func:`run_runner` (runs under its ``--timeout``)."""
    variables = variables or {}
    electron_launch = _build_electron_launch(app_path, app_args, app_user_data_dir)

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
                local_browser=local_browser,
                headful=headful,
                electron_launch=electron_launch,
                deadline=deadline,
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
                keep_artifacts=keep_artifacts,
                electron_launch=electron_launch,
                deadline=deadline,
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
    local_browser: str = "chromium",
    headful: bool = False,
    electron_launch: Optional[ElectronLaunchConfig] = None,
    deadline: Optional[RunDeadline] = None,
) -> None:
    """Local-only suite execution.

    Every definition is fetched up front so a missing use case fails
    before any browser starts.  Each use case then runs through the shared
    ``_execute_usecase_local`` with its own engine — the same path
    ``qa-studio run --usecase-id`` takes.  Any fetch error (including
    secrets) is a runner error (exit 2), never silently tolerated.
    """
    start_time = datetime.utcnow()

    logger.info("Fetching usecases for suite: %s", suite_id)
    suite_usecases = test_suite_api.list_usecases(suite_id)
    logger.info("Found %d usecases in suite", len(suite_usecases))

    if not suite_usecases:
        logger.warning("Suite has no usecases — nothing to execute")
        print("Suite has no usecases to execute.")
        sys.exit(0)

    usecase_ids = [uc.get("usecaseId", uc.get("usecase_id", "")) for uc in suite_usecases]
    definitions: Dict[str, Dict[str, Any]] = {}
    for uc_id in usecase_ids:
        logger.info("Fetching use case: %s", uc_id)
        definitions[uc_id] = usecase_api.get_usecase(uc_id)

    results: List[Dict[str, Any]] = []
    for uc_id in usecase_ids:
        if deadline is not None and deadline.expired():
            logger.info("Skipping use case %s (--timeout)", uc_id)
            results.append({
                "status": "skipped", "usecaseId": uc_id,
                "usecaseName": definitions[uc_id].get("name", uc_id),
                "duration": 0, "steps": [], "artifacts": {}, "error": deadline.message,
            })
            continue
        results.append(_execute_usecase_local(
            usecase_id=uc_id,
            usecase=definitions[uc_id],
            usecase_api=usecase_api,
            base_url=base_url,
            variables=variables,
            region=region,
            model_id=model_id,
            local_browser=local_browser,
            headful=headful,
            electron_launch=electron_launch,
            show_test_name_on_steps=True,
            deadline=deadline,
        ))

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

    exit_code = _apply_timeout(determine_exit_code(summary_results), deadline)
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
    keep_artifacts: bool = False,
    electron_launch: Optional[ElectronLaunchConfig] = None,
    deadline: Optional[RunDeadline] = None,
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
        electron_launch=electron_launch,
        show_test_name_on_steps=True,
        deadline=deadline,
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

    exit_code = _apply_timeout(determine_exit_code(results), deadline)
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
