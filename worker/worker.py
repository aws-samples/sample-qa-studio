#!/usr/bin/env python3
"""
Nova Act Worker - Simple implementation that loads execution data from DynamoDB
and runs Nova Act directly in the same shell.
"""

import os
import logging
import boto3
from nova_act import NovaAct, Workflow
from nova_act.util.s3_writer import S3Writer
from utils import get_region, remove_prefix, get_time
from browser import start_browser, create_browser, delete_browser
import time

from dynamodb_client import DynamoDBClient
from template_parser import TemplateParser
from secrets_client import SecretsClient
from validation_step import execute_validation_step
from secret_step import execute_secret_step
from navigation_step import execute_navigation_step
from retrieve_value_step import execute_retrieve_value_step
from assertion_step import execute_assertion_step
from url_step import execute_url_step
from download_step import execute_download_step

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from nova_act_workflow import ensure_workflow_definition, NOVA_ACT_REGION

def main_batch():
    """Main worker function"""
    
    # Get required environment variables
    usecase_id = os.getenv('USECASE_ID')
    execution_id = os.getenv('EXECUTION_ID')
    s3_bucket_name = os.getenv('S3_BUCKET')
    table_name = os.getenv('DYNAMO_TABLE', 'your-table-name')
    region_name = get_region()
    logs_directory = os.getenv('LOGS_DIRECTORY', './logs')
    
    # Validate required parameters
    if not usecase_id:
        logger.error("USECASE_ID environment variable is required")
        return False
    
    if not execution_id:
        logger.error("EXECUTION_ID environment variable is required")
        return False

    if not s3_bucket_name:
        logger.error("S3_BUCKET environment variable is required")
        return False
    
    logger.info(f"Starting worker for usecase: {usecase_id}, execution: {execution_id}")
    
    # Initialize DynamoDB and Secrets clients
    db_client = DynamoDBClient(table_name, region_name)
    secrets_client = SecretsClient(region_name)
    
    try:
        # Update execution status to executing
        db_client.update_execution_status(usecase_id, execution_id, "executing", executing_at=get_time())

        boto_session = boto3.Session()

        # Create an S3Writer
        s3_writer = S3Writer(
            boto_session=boto_session,
            s3_bucket_name=s3_bucket_name,
            s3_prefix=f"{usecase_id}/{execution_id}/"
        )
        
        # Load execution data
        execution = db_client.get_execution(usecase_id, execution_id)
        if not execution:
            logger.error(f"Execution {execution_id} not found for usecase {usecase_id}")
            return False
        
        logger.info(f"Loaded execution: status={execution.status}, url={execution.starting_url}")
        
        # Load execution steps
        steps = db_client.get_execution_steps(usecase_id, execution_id)
        if not steps:
            logger.error(f"No steps found for execution {execution_id}")
            db_client.update_execution_status(usecase_id, execution_id, "failed", completed_at=get_time())
            return False
        
        logger.info(f"Loaded {len(steps)} steps")
        
        # Load execution variables
        execution_variables = db_client.get_execution_variables(execution_id)
        if execution_variables:
            logger.info(f"Loaded {len(execution_variables.variables)} variables")
        else:
            logger.info("No variables found")
        
        # Load execution headers
        execution_headers = db_client.get_execution_headers(execution_id)
        if execution_headers:
            logger.info(f"Loaded {len(execution_headers.headers)} headers")
        else:
            logger.info("No headers found")
        
        # Load Nova API key from Secrets Manager
        nova_api_key = secrets_client._get_secret_value_by_name(os.getenv('NOVA_ACT_API_KEY_NAME'))
        if not nova_api_key:
            logger.error("Nova API key not found in Secrets Manager")
            return False
        logger.info("Nova API key loaded successfully")
        
        # Initialize template parser (steps will be parsed at runtime)
        template_parser = TemplateParser(execution_id, execution.created_at, execution_variables)
        
        # Log available variables for debugging
        logger.info("Initialized template parser with variables:")
        template_parser.log_available_variables(logger)
        
        # Create execution-specific logs directory
        execution_logs_dir = os.path.join(logs_directory, execution_id)
        os.makedirs(execution_logs_dir, exist_ok=True)
        
        # Execute Nova Act directly in the same shell
        logger.info("Starting execution...")
        logger.info(f"Config: starting_page={execution.starting_url}")
    
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        db_client.update_execution_status(usecase_id, execution_id, "failed", completed_at=get_time())
        return False
        
    # Execute workflow
    try:
        logger.info("Initializing NovaAct context manager...")
        browser_id = create_browser(template_parser.get_all_variables()['UniqueID'], execution_id, s3_bucket_name, f"{usecase_id}/{execution_id}/recording/", execution.region)
        browser = start_browser(browser_id, execution_id, execution.region)
        ws_url, headers = browser.generate_ws_headers()
        live_view_url = browser.generate_live_view_url()
        print(live_view_url)
        
        # Store live view URL in DynamoDB
        db_client.create_live_view(execution_id, live_view_url)

        # Check if using GA service
        use_ga_service = os.getenv('USE_NOVA_ACT_GA', 'false').lower() == 'true'

        if use_ga_service:
            # Nova Act GA Service
            logger.info(f"Using Nova Act GA service in {NOVA_ACT_REGION}")
            workflow_name = ensure_workflow_definition(usecase_id)
            
            # Get model_id from execution, default to nova-act-v1.0
            model_id = getattr(execution, 'model_id', None) or 'nova-act-v1.0'
            logger.info(f"Using model: {model_id}")
            
            with Workflow(
                workflow_definition_name=workflow_name,
                model_id=model_id,
                boto_session_kwargs={
                    "region_name": NOVA_ACT_REGION
                }
            ) as workflow:
                with NovaAct(
                    cdp_endpoint_url=ws_url,
                    cdp_headers=headers,
                    starting_page=execution.starting_url,
                    workflow=workflow,
                    headless=True,
                    logs_directory=execution_logs_dir,
                    ignore_https_errors=True,
                    chrome_channel="chromium",
                    stop_hooks=[s3_writer],
                    user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36')
                ) as nova:
                        all_success = _execute_steps(nova, execution, execution_headers, template_parser, usecase_id, execution_id, s3_bucket_name, db_client, steps)
        else:
            # Nova Act Preview API
            logger.info("Using Nova Act Preview API")
            
            with NovaAct(
                cdp_endpoint_url=ws_url,
                cdp_headers=headers,
                starting_page=execution.starting_url,
                headless=True,
                logs_directory=execution_logs_dir,
                ignore_https_errors=True,
                chrome_channel="chromium",
                stop_hooks=[s3_writer],
                nova_act_api_key=nova_api_key,
                user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36')
            ) as nova:
                all_success = _execute_steps(nova, execution, execution_headers, template_parser, usecase_id, execution_id, s3_bucket_name, db_client, steps)
    
    except Exception as nova_error:
        logger.error(f"Nova Act execution failed: {nova_error}")
        all_success = False
        # Ensure execution status is updated on Nova Act failures
        try:
            db_client.update_execution_status(usecase_id, execution_id, "failed", completed_at=get_time())
        except Exception as db_error:
            logger.error(f"Failed to update execution status after Nova Act error: {str(db_error)}")
        
        # Clean up live view URL on error
        try:
            db_client.delete_live_view(execution_id)
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup live view URL: {str(cleanup_error)}")
        
        return False
    
    browser.stop()
    delete_browser(browser_id, execution.region)
    
    # Clean up live view URL
    db_client.delete_live_view(execution_id)
    
    # Update execution status to completed
    if not all_success:
        db_client.update_execution_status(usecase_id, execution_id, "failed", completed_at=get_time())
        return False

    db_client.update_execution_status(usecase_id, execution_id, "success", completed_at=get_time())
    
    logger.info(f"Execution {execution_id} completed successfully")
    return True


def _execute_steps(nova, execution, execution_headers, template_parser, usecase_id, execution_id, s3_bucket_name, db_client, steps):
    """Execute all steps - extracted to avoid code duplication"""
    all_success = True

    # Set custom HTTP headers if configured
    if execution_headers and execution_headers.headers:
        logger.info(f"Setting {len(execution_headers.headers)} custom HTTP headers")
        
        # Parse headers for variable substitution
        parsed_headers = {}
        for header_name, header_value in execution_headers.headers.items():
            parsed_value = template_parser.parse_instruction(header_value)
            parsed_headers[header_name] = parsed_value
            logger.info(f"Header: {header_name} = {parsed_value}")
        
        nova.page.set_extra_http_headers(parsed_headers)
        # Navigate to starting URL to apply headers
        nova.go_to_url(execution.starting_url)

    logger.info("NovaAct initialized successfully")
        
    # Get the session ID from Nova Act and update the execution record
    session_id = nova.get_session_id()
    logger.info(f"Nova Act session ID: {session_id}")
    
    # Update execution with session ID
    db_client.update_execution_session_id(usecase_id, execution_id, session_id)

    # Execute each step
    for step in steps:
                act_id = ""
                result = None
                status = "success"
                success = True
                logs = ''
                actual_value = ''

                try:
                    # Parse step with current variable context (runtime parsing)
                    parsed_step = template_parser.parse_single_step(step)
                    logger.info(f"Executing step {parsed_step.sort}: {parsed_step.instruction}")
                    
                    match parsed_step.step_type:
                        case 'secret':
                            result, success, logs = execute_secret_step(nova, parsed_step, usecase_id)
                        case 'validation':
                            result, success, logs, actual_value = execute_validation_step(nova, parsed_step)
                        case 'retrieve_value':
                            result, success, logs, actual_value = execute_retrieve_value_step(nova, parsed_step)
                        case 'assertion':
                            result, success, logs, actual_value = execute_assertion_step(parsed_step, template_parser.get_runtime_variables_dict())
                        case 'url':
                            result, success, logs = execute_url_step(nova, parsed_step)
                        case 'download':
                            result, success, logs, actual_value = execute_download_step(nova, parsed_step, usecase_id, execution_id, s3_bucket_name)
                        case _:
                            result, success, logs = execute_navigation_step(nova, parsed_step)

                    # Safely extract act_id from result
                    if result and hasattr(result, 'metadata') and hasattr(result.metadata, 'act_id'):
                        act_id = result.metadata.act_id
                    elif parsed_step.step_type == 'url':
                        act_id = ""
                    else:
                        act_id = ""
                        if success:  # If we thought it was successful but have no result, mark as error
                            success = False
                            logs = f"No valid result returned from step execution. {logs}"

                    if not success:
                        status = "error"
                        all_success = False
                    
                    # Capture runtime variables only for retrieve_value steps
                    if success and parsed_step.step_type == "retrieve_value" and parsed_step.capture_variable and actual_value:
                        runtime_var_name = parsed_step.capture_variable
                        try:
                            template_parser.add_runtime_variable(runtime_var_name, actual_value)
                            logger.info(f"Captured runtime variable: {runtime_var_name} = {actual_value}")
                            
                            # Update runtime variables in database
                            runtime_variables = template_parser.get_runtime_variables()
                            logger.info(f"Updated runtime variables: {runtime_variables}")
                            if runtime_variables:
                                db_client.update_runtime_variables(execution_id, runtime_variables)
                        except Exception as var_error:
                            logger.error(f"Captured runtime variable {runtime_var_name}: {str(var_error)}")
                            # Don't fail the step execution for variable capture errors
                    
                    # Only log parsed_response for steps that return values (validation, retrieve_value)
                    if parsed_step.step_type in ['validation', 'retrieve_value'] and result and hasattr(result, 'parsed_response'):
                        response_text = result.parsed_response
                        logger.info(f"Step: {parsed_step.sort}\tActID:\t{act_id}\tStatus: {status}\tResponse: {response_text}")
                    else:
                        logger.info(f"Step: {parsed_step.sort}\tActID:\t{act_id}\tStatus: {status}")
                    
                except Exception as step_error:
                    logger.error(f"Unexpected error executing step {step.sort}: {str(step_error)}")
                    status = "error"
                    success = False
                    all_success = False
                    act_id = "error"
                    logs = f"Step execution failed with exception: {str(step_error)}"
                    actual_value = ''
                    # Use original step for error handling since parsing might have failed
                    parsed_step = step

                # Always update step status, even on exceptions
                try:
                    db_client.update_execution_step_status(execution_id, remove_prefix(parsed_step.sk, 'EXECUTION_STEP#'), act_id, status, logs, actual_value)
                except Exception as db_error:
                    logger.error(f"Failed to update step status in database: {str(db_error)}")
                    # Continue execution but mark as failed
                    all_success = False

                # Stop execution on first failure
                if not success:
                    logger.info(f"Stopping execution due to failed step {parsed_step.sort}")
                    break
    
    return all_success


def main():
    """Main entry point - routes to batch or wizard mode"""
    worker_mode = os.getenv('WORKER_MODE', 'batch')
    
    if worker_mode == 'wizard':
        logger.info("Starting in wizard mode")
        import wizard_worker
        return wizard_worker.main()
    else:
        logger.info("Starting in batch mode")
        return main_batch()


def main():
    """Main entry point - routes to batch or wizard mode"""
    worker_mode = os.getenv('WORKER_MODE', 'batch')
    
    if worker_mode == 'wizard':
        logger.info("Starting in wizard mode")
        import wizard_worker
        return wizard_worker.main()
    else:
        logger.info("Starting in batch mode")
        return main_batch()

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)