#!/usr/bin/env python3
"""
Nova Act Worker - Simple implementation that loads execution data from DynamoDB
and runs Nova Act directly in the same shell.
"""

import os
import logging
import boto3
import time
from datetime import datetime
from nova_act import NovaAct, Workflow
from nova_act.util.s3_writer import S3Writer
from utils import get_region, remove_prefix, get_time
from browser import start_browser, create_browser, delete_browser

from dynamodb_client import DynamoDBClient
from template_parser import TemplateParser
from secrets_client import SecretsClient
from mobile_actuator import create_mobile_session, cleanup_mobile_session
from validation_step import execute_validation_step
from secret_step import execute_secret_step
from navigation_step import execute_navigation_step
from trajectory_manager import TrajectoryManager
from retrieve_value_step import execute_retrieve_value_step
from assertion_step import execute_assertion_step
from url_step import execute_url_step
from download_step import execute_download_step
from transform_step import execute_transform_step
from browser_step import execute_browser_step
from network_assertion_step import execute_network_assertion_step
from event_emitter import emit_execution_completed_event

# MobileActuator is only available in the Docker image with nova_act_mobile
try:
    from nova_act_mobile.actuation.mobile_actuator import MobileActuator
except ImportError as e:
    import traceback
    print(f"WARNING: Failed to import nova_act_mobile: {e}")
    traceback.print_exc()
    MobileActuator = None

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
    
    # Trajectory replay feature flag (default: enabled)
    enable_trajectory_replay = os.getenv('ENABLE_TRAJECTORY_REPLAY', 'true').lower() != 'false'
    
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
        
        # Check if using GA service
        use_ga_service = os.getenv('USE_NOVA_ACT_GA', 'false').lower() == 'true'
        
        # Load Nova API key from Secrets Manager only if not using GA service
        nova_api_key = None
        if not use_ga_service:
            nova_api_key = secrets_client._get_secret_value_by_name(os.getenv('NOVA_ACT_API_KEY_NAME'))
            if not nova_api_key:
                logger.error("Nova API key not found in Secrets Manager")
                return False
            logger.info("Nova API key loaded successfully")
        else:
            logger.info("Using Nova Act GA service - API key not required")
        
        # Initialize template parser (steps will be parsed at runtime)
        template_parser = TemplateParser(execution_id, execution.created_at, execution_variables)
        
        # Log available variables for debugging
        logger.info("Initialized template parser with variables:")
        template_parser.log_available_variables(logger)
        
        # Create execution-specific logs directory
        execution_logs_dir = os.path.join(logs_directory, execution_id)
        os.makedirs(execution_logs_dir, exist_ok=True)
        
        # Detect trajectory replay support and initialize TrajectoryManager
        replayable_supported = False
        trajectory_manager = None
        if enable_trajectory_replay and execution.enable_cache:
            replayable_supported = TrajectoryManager.detect_replayable_support(NovaAct)
            logger.info(f"Trajectory replay: replayable_supported={replayable_supported}, enable_trajectory_replay={enable_trajectory_replay}")
            
            s3_client = boto3.client('s3', region_name=region_name)
            dynamo_table = db_client.table
            trajectory_manager = TrajectoryManager(
                s3_client=s3_client,
                s3_bucket=s3_bucket_name,
                usecase_id=usecase_id,
                execution_id=execution_id,
                dynamo_table=dynamo_table,
                logs_directory=execution_logs_dir,
                replayable_supported=replayable_supported,
            )
        else:
            logger.info(f"Trajectory replay disabled: enable_trajectory_replay={enable_trajectory_replay}, enable_cache={execution.enable_cache}")
        
        # Execute Nova Act directly in the same shell
        logger.info("Starting execution...")
        logger.info(f"Config: starting_page={execution.starting_url}")
    
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        db_client.update_execution_status(usecase_id, execution_id, "failed", completed_at=get_time())
        return False
        
    # Execute workflow
    # Determine execution path based on test_platform
    test_platform = getattr(execution, 'test_platform', None) or os.getenv('TEST_PLATFORM', 'web')
    is_mobile = test_platform.lower() == 'mobile'

    if is_mobile:
        # ── Mobile Device Farm path ──
        actuator = None
        try:
            logger.info("Using mobile Device Farm execution path")

            if MobileActuator is None:
                raise ImportError("nova_act_mobile is not installed. Cannot run mobile executions.")

            # Create Device Farm actuator
            actuator, session_metadata = create_mobile_session(execution)
            logger.info(f"Mobile session created: {session_metadata}")

            # Store session ARN on execution record (best-effort before NovaAct starts)
            if session_metadata.get('device_farm_session_arn'):
                db_client.update_execution_mobile_metadata(
                    usecase_id, execution_id,
                    device_farm_session_arn=session_metadata['device_farm_session_arn'],
                )

            # Derive app_url from the app identifier
            app_identifier = execution.app_identifier or os.getenv('APP_IDENTIFIER', '')
            starting_page = MobileActuator.app_url(app_identifier)
            logger.info(f"Mobile starting_page: {starting_page}")

            if use_ga_service:
                workflow_name = ensure_workflow_definition(usecase_id)
                model_id = getattr(execution, 'model_id', None) or 'nova-act-v1.0'
                logger.info(f"Using Nova Act GA service (mobile) with model: {model_id}")

                with Workflow(
                    workflow_definition_name=workflow_name,
                    model_id=model_id,
                    boto_session_kwargs={"region_name": NOVA_ACT_REGION},
                ) as workflow:
                    with NovaAct(
                        actuator=actuator,
                        starting_page=starting_page,
                        workflow=workflow,
                        headless=True,
                        logs_directory=execution_logs_dir,
                        stop_hooks=[s3_writer],
                        ignore_https_errors=True,
                        ignore_screen_dims_check=True,
                        record_video=True,
                    ) as nova:
                        all_success = _execute_steps(
                            nova, execution, execution_headers, template_parser,
                            usecase_id, execution_id, s3_bucket_name, db_client, steps,
                        )
            else:
                logger.info("Using Nova Act Preview API (mobile)")
                with NovaAct(
                    actuator=actuator,
                    starting_page=starting_page,
                    headless=True,
                    logs_directory=execution_logs_dir,
                    stop_hooks=[s3_writer],
                    nova_act_api_key=nova_api_key,
                    ignore_https_errors=True,
                    ignore_screen_dims_check=True,
                    record_video=True,
                ) as nova:
                    all_success = _execute_steps(
                        nova, execution, execution_headers, template_parser,
                        usecase_id, execution_id, s3_bucket_name, db_client, steps,
                    )

            # Store device metadata on completion
            try:
                # session_result is cleared after stop(), use stopped_session_arn
                stopped_arn = getattr(actuator, 'stopped_session_arn', None)
                if stopped_arn:
                    db_client.update_execution_mobile_metadata(
                        usecase_id, execution_id,
                        device_farm_session_arn=stopped_arn,
                    )
            except Exception as meta_err:
                logger.warning(f"Failed to store device metadata: {meta_err}")

            # Best-effort: upload mobile recording to S3
            try:
                import glob
                recording_patterns = [
                    os.path.join(execution_logs_dir, '**', '*.mp4'),
                    os.path.join(execution_logs_dir, '**', '*.webm'),
                    os.path.join(execution_logs_dir, '*.mp4'),
                    os.path.join(execution_logs_dir, '*.webm'),
                ]
                for pattern in recording_patterns:
                    for video_file in glob.glob(pattern, recursive=True):
                        s3_client = boto3.client('s3', region_name=region_name)
                        video_filename = os.path.basename(video_file)
                        # Upload to the recording path the frontend expects
                        nova_session_id = getattr(execution, 'nova_session_id', '') or execution_id
                        recording_key = f"{usecase_id}/{execution_id}/recording/{nova_session_id}/{video_filename}"
                        with open(video_file, 'rb') as f:
                            s3_client.put_object(
                                Bucket=s3_bucket_name,
                                Key=recording_key,
                                Body=f,
                                ContentType='video/mp4' if video_file.endswith('.mp4') else 'video/webm',
                            )
                        logger.info(f"Uploaded mobile recording to s3://{s3_bucket_name}/{recording_key}")
            except Exception as rec_err:
                logger.warning(f"Failed to upload mobile recording: {rec_err}")

            # Best-effort: upload Device Farm session logs as an artifact
            try:
                session_logs = getattr(actuator, 'session_logs', None)
                if session_logs:
                    s3_client = boto3.client('s3', region_name=region_name)
                    log_key = f"{usecase_id}/{execution_id}/device_farm_session_logs.txt"
                    s3_client.put_object(
                        Bucket=s3_bucket_name,
                        Key=log_key,
                        Body=session_logs if isinstance(session_logs, (bytes, str)) else str(session_logs),
                        ContentType='text/plain',
                    )
                    logger.info(f"Uploaded Device Farm session logs to s3://{s3_bucket_name}/{log_key}")
            except Exception as log_err:
                logger.warning(f"Failed to upload Device Farm session logs: {log_err}")

        except Exception as mobile_error:
            logger.error(f"Mobile execution failed: {mobile_error}")
            all_success = False

            # Check for 5-minute timeout on session start
            error_msg = str(mobile_error)
            if 'timeout' in error_msg.lower() or 'RUNNING' in error_msg:
                logger.error("Device Farm session timed out waiting for RUNNING state")
                error_msg = f"Device Farm session failed to reach RUNNING state within 5 minutes: {error_msg}"

            try:
                completed_at = get_time()
                db_client.update_execution_status(usecase_id, execution_id, "failed", completed_at=completed_at)
                db_client.update_suite_execution_counters(execution_id, usecase_id, "failed")
                emit_execution_completed_event(usecase_id, execution_id, "failed", region_name)
            except Exception as db_error:
                logger.error(f"Failed to update execution status after mobile error: {db_error}")

            return False

        finally:
            # Always clean up the Device Farm session
            cleanup_mobile_session(actuator)

            # Enqueue async video download (5 min delay for Device Farm to finalize)
            try:
                stopped_arn = getattr(actuator, 'stopped_session_arn', None)
                recording_queue_url = os.getenv('RECORDING_QUEUE_URL')
                if stopped_arn and recording_queue_url:
                    import json as _json
                    sqs_client = boto3.client('sqs', region_name=region_name)
                    nova_session_id = getattr(execution, 'nova_session_id', '') or execution_id
                    sqs_client.send_message(
                        QueueUrl=recording_queue_url,
                        MessageBody=_json.dumps({
                            'session_arn': stopped_arn,
                            'usecase_id': usecase_id,
                            'execution_id': execution_id,
                            'nova_session_id': nova_session_id,
                        }),
                        DelaySeconds=300,
                    )
                    logger.info(f"Enqueued recording download for session {stopped_arn} (5 min delay)")
                elif not recording_queue_url:
                    logger.debug("RECORDING_QUEUE_URL not set, skipping recording enqueue")
            except Exception as enqueue_err:
                logger.warning(f"Failed to enqueue recording download: {enqueue_err}")

    else:
        # ── Web AgentCore Browser path (existing logic, unchanged) ──
        try:
            logger.info("Initializing NovaAct context manager...")
            # Create browser with network configuration (VPC settings from CDK stack environment variables or PUBLIC mode)
            browser_id = create_browser(template_parser.get_all_variables()['UniqueID'], execution_id, s3_bucket_name, f"{usecase_id}/{execution_id}/recording/", execution.region, browser_policy_s3_path=getattr(execution, 'browser_policy_s3_path', None))
            browser = start_browser(browser_id, execution_id, execution.region)
            ws_url, headers = browser.generate_ws_headers()
            live_view_url = browser.generate_live_view_url()
            print(live_view_url)
            
            # Store live view URL in DynamoDB
            db_client.create_live_view(execution_id, live_view_url)

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
                    # Build NovaAct kwargs, conditionally adding replayable
                    nova_kwargs = dict(
                        cdp_endpoint_url=ws_url,
                        cdp_headers=headers,
                        starting_page=execution.starting_url,
                        workflow=workflow,
                        headless=True,
                        logs_directory=execution_logs_dir,
                        ignore_https_errors=True,
                        chrome_channel="chromium",
                        stop_hooks=[s3_writer],
                    )
                    if replayable_supported and enable_trajectory_replay and execution.enable_cache:
                        nova_kwargs['replayable'] = True
                        logger.info("Trajectory recording enabled: passing replayable=True to NovaAct (GA)")
                    
                    with NovaAct(**nova_kwargs) as nova:
                            all_success = _execute_steps(nova, execution, execution_headers, template_parser, usecase_id, execution_id, s3_bucket_name, db_client, steps, trajectory_manager)
            else:
                # Nova Act Preview API
                logger.info("Using Nova Act Preview API")
                
                # Build NovaAct kwargs, conditionally adding replayable
                nova_kwargs = dict(
                    cdp_endpoint_url=ws_url,
                    cdp_headers=headers,
                    starting_page=execution.starting_url,
                    headless=True,
                    logs_directory=execution_logs_dir,
                    ignore_https_errors=True,
                    chrome_channel="chromium",
                    stop_hooks=[s3_writer],
                    nova_act_api_key=nova_api_key,
                )
                if replayable_supported and enable_trajectory_replay and execution.enable_cache:
                    nova_kwargs['replayable'] = True
                    logger.info("Trajectory recording enabled: passing replayable=True to NovaAct (Preview)")
                
                with NovaAct(**nova_kwargs) as nova:
                    all_success = _execute_steps(nova, execution, execution_headers, template_parser, usecase_id, execution_id, s3_bucket_name, db_client, steps, trajectory_manager)
        
        except Exception as nova_error:
            logger.error(f"Nova Act execution failed: {nova_error}")
            all_success = False
            # Ensure execution status is updated on Nova Act failures
            try:
                completed_at = get_time()
                db_client.update_execution_status(usecase_id, execution_id, "failed", completed_at=completed_at)
                # Update suite execution counters if part of a suite
                db_client.update_suite_execution_counters(execution_id, usecase_id, "failed")
                
                # Emit event after failed execution
                emit_execution_completed_event(usecase_id, execution_id, "failed", region_name)
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
        # Update suite execution counters if part of a suite
        db_client.update_suite_execution_counters(execution_id, usecase_id, "failed")
        
        # Emit event after failed execution
        emit_execution_completed_event(usecase_id, execution_id, "failed", region_name)
        
        return False

    db_client.update_execution_status(usecase_id, execution_id, "success", completed_at=get_time())
    # Update suite execution counters if part of a suite
    db_client.update_suite_execution_counters(execution_id, usecase_id, "success")
    
    # Emit event after successful execution
    emit_execution_completed_event(usecase_id, execution_id, "success", region_name)
    
    logger.info(f"Execution {execution_id} completed successfully")
    return True


def _execute_steps(nova, execution, execution_headers, template_parser, usecase_id, execution_id, s3_bucket_name, db_client, steps, trajectory_manager=None):
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
                        case 'transform':
                            result, success, logs, actual_value = execute_transform_step(parsed_step, template_parser)
                        case 'browser':
                            result, success, logs = execute_browser_step(nova, parsed_step)
                        case 'network_assertion':
                            result, success, logs, actual_value = execute_network_assertion_step(nova, parsed_step)
                        case _:
                            result, success, logs = execute_navigation_step(nova, parsed_step, execution.enable_cache, trajectory_manager)

                    # Safely extract act_id from result
                    if result and hasattr(result, 'metadata') and hasattr(result.metadata, 'act_id'):
                        act_id = result.metadata.act_id
                    elif parsed_step.step_type in ('url', 'transform', 'browser'):
                        act_id = ""
                    else:
                        act_id = ""
                        if success:  # If we thought it was successful but have no result, mark as error
                            success = False
                            logs = f"No valid result returned from step execution. {logs}"

                    if not success:
                        status = "error"
                        all_success = False
                    
                    # Capture runtime variables for retrieve_value and transform steps
                    if success and parsed_step.step_type in ("retrieve_value", "transform") and parsed_step.capture_variable and actual_value:
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