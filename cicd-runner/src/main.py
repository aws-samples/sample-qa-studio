"""Main runner execution logic."""

import sys
import logging
import asyncio
import boto3
from typing import Dict, Optional, List, Any
from datetime import datetime
from .auth.oauth_client import OAuthClient
from .api.client import APIClient
from .api.test_suites import TestSuiteAPI
from .api.executions import ExecutionAPI
from .execution.engine import ExecutionEngine
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
