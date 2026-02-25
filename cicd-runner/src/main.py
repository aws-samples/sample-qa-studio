"""Main runner execution logic."""

import sys
import json
import logging
import asyncio
import shutil
import boto3
from pathlib import Path
from typing import Dict, Optional, List, Any
from datetime import datetime
from .auth.oauth_client import OAuthClient
from .api.client import APIClient
from .api.test_suites import TestSuiteAPI
from .api.executions import ExecutionAPI
from .api.usecases import UseCaseAPI
from .execution.engine import ExecutionEngine
from .execution.models import LocalExecutionResult, LocalStepResult, LocalArtifacts
from .execution.suite_log_capture import SuiteLogCapture
from .execution.artifact_uploader import ArtifactUploader
from .output.summary import SummaryFormatter
from .config.settings import Settings
from .utils.errors import RunnerError, sanitize_error_message

logger = logging.getLogger(__name__)


def determine_exit_code(results: List[Dict[str, Any]]) -> int:
    """
    Determine exit code based on execution results.
    
    Args:
        results: List of execution results
    
    Returns:
        Exit code:
        - 0: All tests passed
        - 1: One or more tests failed
        - 2: Runner error (no results)
    """
    if not results:
        return 2  # Error: no results
    
    for r in results:
        if r['status'] == 'failed':
            return 1  # Failure: one or more failed
    
    return 0  # Success: all passed

def validate_aws_session() -> None:
    """
    Validate that a working AWS session exists.
    Nova Act requires valid AWS credentials for Bedrock access.

    Raises:
        RunnerError: If AWS credentials are missing or invalid
    """
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        logger.info(f"AWS session valid - Account: {identity['Account']}, ARN: {identity['Arn']}")
    except Exception as e:
        raise RunnerError(
            "No valid AWS session found. Nova Act requires AWS credentials "
            "for Bedrock access. Please configure AWS credentials via environment "
            "variables (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY), AWS SSO, "
            f"or an IAM role. Error: {sanitize_error_message(str(e))}"
        )




def run_usecase_local(
    usecase_id: str,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    timeout: int,
    output_format: str = "json",
) -> None:
    """
    Execute a single use case in local-only mode.

    Fetches the use case definition from the API, executes locally via
    Nova Act, stores artifacts on the local filesystem, and outputs
    structured JSON to stdout. No execution records, no S3 uploads,
    no status updates.

    Args:
        usecase_id: Use case UUID
        base_url: Optional base URL override for starting_url
        variables: Variable overrides (CLI takes precedence)
        region: Optional AWS region override
        model_id: Optional model ID override
        timeout: Global timeout in seconds

    Raises:
        SystemExit: Exit code 0 on success, 1 on failure, 2 on error
    """
    try:
        # Load configuration from environment
        logger.info("Loading configuration from environment variables...")
        settings = Settings.from_env()

        # Validate AWS session early — Nova Act needs it for Bedrock
        logger.info("Validating AWS session...")
        validate_aws_session()

        # Initialize OAuth client and authenticate
        logger.info("Initializing OAuth client...")
        oauth_client = OAuthClient(
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
            token_endpoint=settings.oauth_token_endpoint,
        )
        logger.info("Authenticating with OAuth client credentials...")
        oauth_client.get_access_token()
        logger.info("Successfully authenticated")

        # Initialize API clients
        logger.info("Initializing API client...")
        api_client = APIClient(settings.api_endpoint, oauth_client)
        usecase_api = UseCaseAPI(api_client)

        # Fetch use case definition
        logger.info(f"Fetching use case definition: {usecase_id}")
        usecase = usecase_api.get_usecase(usecase_id)
        steps = usecase_api.get_steps(usecase_id)
        uc_variables = usecase_api.get_variables(usecase_id)
        secrets = usecase_api.get_secrets(usecase_id)
        logger.info(f"Found use case: {usecase.get('name', '')} with {len(steps)} steps")

        # Apply overrides
        if base_url:
            usecase['starting_url'] = base_url
        merged_vars = {**uc_variables, **variables}
        if region:
            usecase['executing_region'] = region
        if model_id:
            usecase['model_id'] = model_id

        # Prepare artifact directory
        artifact_dir = Path('/tmp/qa-studio-artifacts') / usecase_id
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # Compose use case definition for the engine
        usecase_definition = {
            'usecase_id': usecase_id,
            'name': usecase.get('name', ''),
            'starting_url': usecase.get('starting_url', ''),
            'executing_region': usecase.get('executing_region', 'us-east-1'),
            'model_id': usecase.get('model_id', 'nova-act-v1.0'),
            'steps': steps,
            'variables': merged_vars,
            'secrets': secrets,
        }

        # Execute via engine
        # ExecutionEngine.execute_usecase_local() will be implemented in Task 7
        execution_api = ExecutionAPI(api_client)
        engine = ExecutionEngine(execution_api, suite_execution_id='local', keep_artifacts=True)
        result = asyncio.run(engine.execute_usecase_local(
            usecase_definition=usecase_definition,
            usecase_id=usecase_id,
            artifact_dir=artifact_dir,
            region=usecase_definition['executing_region'],
            model_id=usecase_definition['model_id'],
        ))

        # Build LocalExecutionResult from engine output
        step_results = [
            LocalStepResult(
                step_id=s.get('step_id', ''),
                instruction=s.get('instruction', ''),
                status=s.get('status', 'failed'),
                duration=s.get('duration', 0.0),
                screenshot=s.get('screenshot'),
            )
            for s in result.get('steps', [])
        ]

        artifacts = LocalArtifacts(
            video=result.get('artifacts', {}).get('video'),
            logs=result.get('artifacts', {}).get('logs'),
        )

        execution_result = LocalExecutionResult(
            status=result.get('status', 'failed'),
            usecase_id=usecase_id,
            usecase_name=usecase_definition['name'],
            duration=result.get('duration', 0.0),
            steps=step_results,
            artifacts=artifacts,
        )

        # Write output to stdout (logs go to stderr via logging)
        if output_format == "summary":
            print("\n" + SummaryFormatter.format_local_summary(execution_result) + "\n")
        else:
            print(execution_result.model_dump_json(by_alias=True))

        # Exit with appropriate code
        exit_code = 0 if execution_result.status == 'success' else 1
        sys.exit(exit_code)

    except Exception as e:
        sanitized_error = sanitize_error_message(str(e))
        logger.error(f"Runner failed: {sanitized_error}", exc_info=True)
        sys.exit(2)


def run_usecase(
    usecase_id: str,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    timeout: int,
    keep_artifacts: bool = False,
) -> None:
    """
    Execute a single use case in normal mode (with server-side tracking).

    Creates an execution record via the API, then follows the existing
    execution flow: fetch steps, execute via Nova Act, upload artifacts,
    update status.

    Args:
        usecase_id: Use case UUID
        base_url: Optional base URL override
        variables: Variable overrides
        region: Optional AWS region override
        model_id: Optional model ID override
        timeout: Global timeout in seconds
        keep_artifacts: Whether to keep local artifact files

    Raises:
        SystemExit: Exit code 0 on success, 1 on failure, 2 on error
    """
    try:
        # Load configuration from environment
        logger.info("Loading configuration from environment variables...")
        settings = Settings.from_env()

        # Validate AWS session early — Nova Act needs it for Bedrock
        logger.info("Validating AWS session...")
        validate_aws_session()

        # Initialize OAuth client and authenticate
        logger.info("Initializing OAuth client...")
        oauth_client = OAuthClient(
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
            token_endpoint=settings.oauth_token_endpoint,
        )
        logger.info("Authenticating with OAuth client credentials...")
        oauth_client.get_access_token()
        logger.info("Successfully authenticated")

        # Initialize API clients
        logger.info("Initializing API client...")
        api_client = APIClient(settings.api_endpoint, oauth_client)
        usecase_api = UseCaseAPI(api_client)

        # Fetch use case metadata (for the name)
        logger.info(f"Fetching use case: {usecase_id}")
        usecase = usecase_api.get_usecase(usecase_id)
        logger.info(f"Found use case: {usecase.get('name', '')}")

        # Create execution record
        logger.info("Creating execution record...")
        execution_response = usecase_api.execute_usecase(
            usecase_id=usecase_id,
            base_url=base_url,
            variables=variables if variables else None,
            region=region,
            model_id=model_id,
        )
        execution_id = execution_response.get('execution_id', '')
        logger.info(f"Execution record created: {execution_id}")

        # Record start time
        start_time = datetime.utcnow()

        # Initialize ExecutionEngine and ExecutionAPI
        logger.info("Initializing execution engine...")
        execution_api = ExecutionAPI(api_client)
        engine = ExecutionEngine(
            execution_api,
            suite_execution_id=execution_id,
            keep_artifacts=keep_artifacts,
        )

        # Execute using existing engine flow
        execution = {
            'execution_id': execution_id,
            'usecase_id': usecase_id,
            'usecase_name': usecase.get('name', ''),
        }
        result = asyncio.run(engine.execute_usecase(execution))

        # Record end time
        end_time = datetime.utcnow()

        # Format and print summary
        logger.info("Generating execution summary...")
        summary = SummaryFormatter.format_table(
            suite_name=usecase.get('name', ''),
            suite_execution_id=execution_id,
            results=[result],
            start_time=start_time,
            end_time=end_time,
        )
        print("\n" + summary + "\n")

        # Determine exit code
        exit_code = determine_exit_code([result])
        logger.info(f"Execution completed with exit code: {exit_code}")
        sys.exit(exit_code)

    except Exception as e:
        sanitized_error = sanitize_error_message(str(e))
        logger.error(f"Runner failed: {sanitized_error}", exc_info=True)
        sys.exit(2)


def run_runner(
    suite_id: str,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    timeout: int,
    keep_artifacts: bool = False
) -> None:
    """
    Main runner execution logic.
    
    Args:
        suite_id: Test suite UUID
        base_url: Optional base URL override
        variables: Variable overrides
        region: Optional AWS region override
        model_id: Optional model ID override
        timeout: Global timeout in seconds
        
    Raises:
        SystemExit: Exit code 0 on success, 1 on failure, 2 on error
    """
    try:
        # Load configuration from environment
        logger.info("Loading configuration from environment variables...")
        settings = Settings.from_env()
        
        # Validate AWS session early — Nova Act needs it for Bedrock
        logger.info("Validating AWS session...")
        validate_aws_session()
        
        # Initialize OAuth client
        logger.info("Initializing OAuth client...")
        oauth_client = OAuthClient(
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
            token_endpoint=settings.oauth_token_endpoint
        )
        
        # Authenticate
        logger.info("Authenticating with OAuth client credentials...")
        oauth_client.get_access_token()
        logger.info("Successfully authenticated")
        
        # Initialize API client
        logger.info("Initializing API client...")
        api_client = APIClient(settings.api_endpoint, oauth_client)
        test_suite_api = TestSuiteAPI(api_client)
        
        # Fetch test suite
        logger.info(f"Fetching test suite: {suite_id}")
        suite = test_suite_api.get_suite(suite_id)
        logger.info(f"Found test suite: {suite['name']}")
        
        # Execute test suite
        logger.info("Creating execution records...")
        execution_response = test_suite_api.execute_suite(
            suite_id=suite_id,
            base_url=base_url,
            variables=variables,
            region=region,
            model_id=model_id
        )
        
        suite_execution_id = execution_response['suite_execution_id']
        execution_ids = execution_response['execution_ids']
        
        logger.info(f"Suite execution created: {suite_execution_id}")
        logger.info(f"Created {len(execution_ids)} execution records")
        
        # Record start time
        start_time = datetime.utcnow()
        
        # Initialize ExecutionEngine and ExecutionAPI
        logger.info("Initializing execution engine...")
        execution_api = ExecutionAPI(api_client)
        execution_engine = ExecutionEngine(execution_api, suite_execution_id, keep_artifacts=keep_artifacts)
        
        # Start suite-level log capture
        suite_log_capture = SuiteLogCapture(suite_execution_id)
        suite_log_capture.start()
        
        # Execute all use cases in parallel
        logger.info("Executing use cases in parallel...")
        results = asyncio.run(execution_engine.execute_all(execution_ids))
        
        # Record end time
        end_time = datetime.utcnow()
        
        # Update suite execution status based on results
        logger.info("Updating suite execution status...")
        try:
            if not results:
                suite_status = 'failed'
            elif all(r['status'] == 'success' for r in results):
                suite_status = 'completed'
            elif any(r['status'] == 'success' for r in results):
                suite_status = 'partial'
            else:
                suite_status = 'failed'
            
            asyncio.run(execution_api.update_suite_status(
                suite_id=suite_id,
                suite_execution_id=suite_execution_id,
                status=suite_status
            ))
            logger.info(f"Suite execution status updated to: {suite_status}")
        except Exception as e:
            logger.warning(f"Failed to update suite execution status: {e}")
        
        # Format and print summary table to stdout
        logger.info("Generating execution summary...")
        summary = SummaryFormatter.format_table(
            suite_name=suite['name'],
            suite_execution_id=suite_execution_id,
            results=results,
            start_time=start_time,
            end_time=end_time
        )
        print("\n" + summary + "\n")
        
        # Determine and return exit code
        exit_code = determine_exit_code(results)
        logger.info(f"Execution completed with exit code: {exit_code}")
        
        # Stop suite log capture and upload
        suite_log_path = suite_log_capture.stop()
        if suite_log_path:
            try:
                artifact_uploader = ArtifactUploader(api_client)
                asyncio.run(artifact_uploader.upload_suite_artifacts(
                    suite_id=suite_id,
                    suite_execution_id=suite_execution_id,
                    artifacts={'logs': suite_log_path},
                ))
            except Exception as e:
                logger.warning(f"Failed to upload suite logs: {e}")
        
        sys.exit(exit_code)
        
    except Exception as e:
        sanitized_error = sanitize_error_message(str(e))
        logger.error(f"Runner failed: {sanitized_error}", exc_info=True)
        # Ensure suite log capture is stopped on error
        if 'suite_log_capture' in locals():
            suite_log_capture.stop()
        sys.exit(2)
