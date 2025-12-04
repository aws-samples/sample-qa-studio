#!/usr/bin/env python3
"""
Wizard Worker - Interactive step-by-step execution mode
Maintains a persistent browser session and executes steps on demand via SQS commands
"""

import os
import logging
import boto3
import json
import time
from nova_act import NovaAct, Workflow
from nova_act.util.s3_writer import S3Writer
from utils import get_region, get_time
from browser import start_browser, create_browser, delete_browser

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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

INACTIVITY_TIMEOUT = 30 * 60  # 30 minutes in seconds
from nova_act_workflow import ensure_workflow_definition, NOVA_ACT_REGION

def execute_single_step(nova, step, template_parser, usecase_id, execution_id, s3_bucket_name, db_client):
    """Execute a single step and return results"""
    act_id = ""
    result = None
    status = "success"
    success = True
    logs = ''
    actual_value = ''

    try:
        # Parse step with current variable context
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

        # Extract act_id from result
        if result and hasattr(result, 'metadata') and hasattr(result.metadata, 'act_id'):
            act_id = result.metadata.act_id
        elif parsed_step.step_type == 'url':
            act_id = ""
        else:
            act_id = ""
            if success:
                success = False
                logs = f"No valid result returned from step execution. {logs}"

        if not success:
            status = "error"
        
        # Capture runtime variables for retrieve_value steps
        if success and parsed_step.step_type == "retrieve_value" and parsed_step.capture_variable and actual_value:
            runtime_var_name = parsed_step.capture_variable
            try:
                template_parser.add_runtime_variable(runtime_var_name, actual_value)
                logger.info(f"Captured runtime variable: {runtime_var_name} = {actual_value}")
                
                runtime_variables = template_parser.get_runtime_variables()
                if runtime_variables:
                    db_client.update_runtime_variables(execution_id, runtime_variables)
            except Exception as var_error:
                logger.error(f"Failed to capture runtime variable {runtime_var_name}: {str(var_error)}")
        
        # Only log parsed_response for steps that return values (validation, retrieve_value)
        if parsed_step.step_type in ['validation', 'retrieve_value'] and result and hasattr(result, 'parsed_response'):
            response_text = result.parsed_response
            logger.info(f"Step: {parsed_step.sort}\tActID:\t{act_id}\tStatus: {status}\tResponse: {response_text}")
        else:
            logger.info(f"Step: {parsed_step.sort}\tActID:\t{act_id}\tStatus: {status}")
        
    except Exception as step_error:
        logger.error(f"Unexpected error executing step: {str(step_error)}")
        status = "error"
        success = False
        act_id = "error"
        logs = f"Step execution failed with exception: {str(step_error)}"
        actual_value = ''

    return act_id, status, success, logs, actual_value


def main():
    """Main wizard worker function"""
    
    session_id = os.getenv('SESSION_ID')
    usecase_id = os.getenv('USECASE_ID')
    wizard_queue_url = os.getenv('WIZARD_QUEUE_URL')
    s3_bucket_name = os.getenv('S3_BUCKET')
    table_name = os.getenv('DYNAMODB_TABLE_NAME')
    region_name = get_region()
    logs_directory = os.getenv('LOGS_DIRECTORY', './logs')
    
    if not all([session_id, usecase_id, wizard_queue_url, s3_bucket_name]):
        logger.error("Missing required environment variables")
        return False
    
    logger.info(f"Starting wizard worker for session: {session_id}, usecase: {usecase_id}")
    
    # Create execution-specific logs directory
    execution_logs_dir = os.path.join(logs_directory, session_id)
    os.makedirs(execution_logs_dir, exist_ok=True)
    logger.info(f"Logs directory: {execution_logs_dir}")
    
    # Initialize clients
    db_client = DynamoDBClient(table_name, region_name)
    secrets_client = SecretsClient(region_name)
    sqs_client = boto3.client('sqs', region_name=region_name)
    boto_session = boto3.Session()
    
    try:
        # Update execution status
        db_client.update_execution_status(usecase_id, session_id, "executing", executing_at=get_time())
        
        # Load execution data
        execution = db_client.get_execution(usecase_id, session_id)
        if not execution:
            logger.error(f"Execution {session_id} not found for usecase {usecase_id}")
            db_client.update_execution_status(usecase_id, session_id, "failed", completed_at=get_time())
            return False
        
        if not execution.starting_url:
            logger.error(f"Execution {session_id} missing starting_url field")
            db_client.update_execution_status(usecase_id, session_id, "failed", completed_at=get_time())
            return False
        
        logger.info(f"Loaded execution: status={execution.status}, url={execution.starting_url}")
        
        # Load execution variables
        execution_variables = db_client.get_execution_variables(session_id)
        if execution_variables:
            logger.info(f"Loaded {len(execution_variables.variables)} variables")
        
        # Load execution headers
        execution_headers = db_client.get_execution_headers(session_id)
        if execution_headers:
            logger.info(f"Loaded {len(execution_headers.headers)} headers")
        
        # Load Nova API key
        nova_api_key = secrets_client._get_secret_value_by_name(os.getenv('NOVA_ACT_API_KEY_NAME'))
        if not nova_api_key:
            logger.error("Nova API key not found")
            return False
        
        # Initialize template parser
        template_parser = TemplateParser(session_id, execution.created_at, execution_variables)
        template_parser.log_available_variables(logger)
        
        # Create S3Writer
        s3_writer = S3Writer(
            boto_session=boto_session,
            s3_bucket_name=s3_bucket_name,
            s3_prefix=f"{usecase_id}/{session_id}/"
        )
        
        # Create browser
        logger.info("Creating browser session...")
        browser_id = create_browser(
            template_parser.get_all_variables()['UniqueID'],
            session_id,
            s3_bucket_name,
            f"{usecase_id}/{session_id}/recording/",
            execution.region
        )
        browser = start_browser(browser_id, session_id, execution.region)
        ws_url, headers = browser.generate_ws_headers()
        live_view_url = browser.generate_live_view_url()
        
        logger.info(f"Live view URL: {live_view_url}")
        db_client.create_live_view(session_id, live_view_url)
        
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
                    headless=execution.headless,
                    logs_directory=execution_logs_dir,
                    ignore_https_errors=True,
                    chrome_channel="chromium",
                    stop_hooks=[s3_writer],
                    user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0')
                ) as nova:
                    
                    # Set custom HTTP headers if configured
                    if execution_headers and execution_headers.headers:
                        logger.info(f"Setting {len(execution_headers.headers)} custom HTTP headers")
                        parsed_headers = {}
                        for header_name, header_value in execution_headers.headers.items():
                            parsed_value = template_parser.parse_instruction(header_value)
                            parsed_headers[header_name] = parsed_value
                        nova.page.set_extra_http_headers(parsed_headers)
                        nova.go_to_url(execution.starting_url)
                    
                    logger.info("NovaAct initialized successfully")
                    
                    # Get session ID and update execution
                    session_id_nova = nova.get_session_id()
                    logger.info(f"Nova Act session ID: {session_id_nova}")
                    db_client.update_execution_session_id(usecase_id, session_id, session_id_nova)
                    
                    # Update last activity
                    last_activity = time.time()
                    db_client.update_execution_last_activity(usecase_id, session_id, get_time())
                    
                    # Main command loop
                    logger.info("Entering command loop...")
                    use_eventbridge = os.getenv('USE_EVENTBRIDGE_COMMANDS', 'true').lower() == 'true'
                    logger.info(f"Command mode: {'EventBridge/DynamoDB' if use_eventbridge else 'SQS'}")
                    
                    while True:
                        # Check for inactivity timeout
                        if time.time() - last_activity > INACTIVITY_TIMEOUT:
                            logger.info("Inactivity timeout reached, terminating session")
                            db_client.update_execution_status(usecase_id, session_id, "timeout", completed_at=get_time())
                            break
                        
                        try:
                            command = None
                            
                            if use_eventbridge:
                                # Poll DynamoDB for commands (EventBridge mode)
                                commands = db_client.poll_wizard_commands(session_id, limit=1)
                                
                                if not commands:
                                    # No commands, sleep briefly and continue
                                    time.sleep(1)
                                    continue
                                
                                command_record = commands[0]
                                command = {
                                    'action': command_record.get('action'),
                                    'sessionId': command_record.get('sessionId') or command_record.get('session_id'),
                                    'stepId': command_record.get('stepId') or command_record.get('step_id'),
                                    'step_id': command_record.get('stepId') or command_record.get('step_id')  # For compatibility
                                }
                                
                                logger.info(f"Received command from DynamoDB for session {session_id}")
                                logger.info(f"Command details: {json.dumps(command, indent=2)}")
                                logger.info(f"Full command record: {json.dumps(command_record, indent=2, default=str)}")
                                
                                # Delete command from DynamoDB after reading
                                db_client.delete_wizard_command(session_id, command_record['sk'])
                                
                                last_activity = time.time()
                                db_client.update_execution_last_activity(usecase_id, session_id, get_time())
                                
                            else:
                                # Poll SQS for commands (legacy mode)
                                response = sqs_client.receive_message(
                                    QueueUrl=wizard_queue_url,
                                    MaxNumberOfMessages=1,
                                    WaitTimeSeconds=20,
                                    MessageAttributeNames=['All']
                                )
                                
                                if 'Messages' not in response:
                                    continue
                                
                                message = response['Messages'][0]
                                command = json.loads(message['Body'])
                                command_session_id = command.get('session_id') or command.get('SessionID')
                                
                                # Validate this message is for our session
                                if command_session_id != session_id:
                                    logger.warning(f"Ignoring command for different session: {command_session_id} (ours: {session_id})")
                                    continue
                                
                                logger.info(f"Received command from SQS for session {session_id}")
                                logger.info(f"Command details: {json.dumps(command, indent=2)}")
                                
                                # Delete message from queue
                                sqs_client.delete_message(
                                    QueueUrl=wizard_queue_url,
                                    ReceiptHandle=message['ReceiptHandle']
                                )
                                
                                last_activity = time.time()
                                db_client.update_execution_last_activity(usecase_id, session_id, get_time())
                            
                            # Process command (unified for both modes)
                            if not command:
                                continue
                            
                            logger.info(f"Processing command: {command['action']}")
                            
                            if command['action'] == 'execute_step':
                                # Get step from DynamoDB
                                step_id = command['step_id']
                                step = db_client.get_execution_step(session_id, step_id)
                                
                                if step:
                                    act_id, status, success, logs, actual_value = execute_single_step(
                                        nova, step, template_parser, usecase_id, session_id, s3_bucket_name, db_client
                                    )
                                    
                                    # Update step status
                                    db_client.update_execution_step_status(
                                        session_id, step_id, act_id, status, logs, actual_value
                                    )
                                else:
                                    logger.error(f"Step {step_id} not found")
                            
                            elif command['action'] == 'restart':
                                logger.info("Restarting wizard session...")
                                # Close current browser
                                nova.close()
                                browser.stop()
                                delete_browser(browser_id, execution.region)
                                
                                # Create new browser
                                browser_id = create_browser(
                                    template_parser.get_all_variables()['UniqueID'],
                                    session_id,
                                    s3_bucket_name,
                                    f"{usecase_id}/{session_id}/recording/",
                                    execution.region
                                )
                                browser = start_browser(browser_id, session_id, execution.region)
                                ws_url, headers = browser.generate_ws_headers()
                                live_view_url = browser.generate_live_view_url()
                                db_client.create_live_view(session_id, live_view_url)
                                
                                # Reinitialize NovaAct (Preview API mode)
                                nova = NovaAct(
                                    cdp_endpoint_url=ws_url,
                                    cdp_headers=headers,
                                    starting_page=execution.starting_url,
                                    headless=execution.headless,
                                    logs_directory=execution_logs_dir,
                                    ignore_https_errors=True,
                                    chrome_channel="chromium",
                                    stop_hooks=[s3_writer],
                                    nova_act_api_key=nova_api_key,
                                    user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0')
                                )
                                nova.__enter__()
                                
                                # Replay accepted steps
                                accepted_steps = db_client.get_accepted_execution_steps(session_id)
                                logger.info(f"Replaying {len(accepted_steps)} accepted steps")
                                
                                for step in accepted_steps:
                                    act_id, status, success, logs, actual_value = execute_single_step(
                                        nova, step, template_parser, usecase_id, session_id, s3_bucket_name, db_client
                                    )
                                    if not success:
                                        logger.error(f"Failed to replay step {step.sort}")
                                        break
                                
                                logger.info("Restart complete")
                            
                            elif command['action'] == 'terminate':
                                logger.info("Terminating wizard session - starting graceful shutdown")
                                
                                # Update execution status to success (wizard completed successfully)
                                db_client.update_execution_status(usecase_id, session_id, "success", completed_at=get_time())
                                
                                # Close browser gracefully
                                try:
                                    logger.info("Closing NovaAct session...")
                                    nova.close()
                                except Exception as close_err:
                                    logger.error(f"Error closing NovaAct: {close_err}")
                        
                                # Stop browser
                                try:
                                    logger.info("Stopping browser...")
                                    browser.stop()
                                except Exception as stop_err:
                                    logger.error(f"Error stopping browser: {stop_err}")
                                
                                # Delete browser
                                try:
                                    logger.info("Deleting browser...")
                                    delete_browser(browser_id, execution.region)
                                except Exception as delete_err:
                                    logger.error(f"Error deleting browser: {delete_err}")
                                
                                # Delete live view
                                try:
                                    logger.info("Deleting live view...")
                                    db_client.delete_live_view(session_id)
                                except Exception as lv_err:
                                    logger.error(f"Error deleting live view: {lv_err}")
                                
                                logger.info("Graceful shutdown complete - exiting")
                                break
                        
                        except Exception as e:
                            logger.error(f"Error in command loop: {e}")
                            continue
        else:
            # Nova Act Preview API
            logger.info("Using Nova Act Preview API")
            
            with NovaAct(
                cdp_endpoint_url=ws_url,
                cdp_headers=headers,
                starting_page=execution.starting_url,
                headless=execution.headless,
                logs_directory=execution_logs_dir,
                ignore_https_errors=True,
                chrome_channel="chromium",
                stop_hooks=[s3_writer],
                nova_act_api_key=nova_api_key,
                user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0')
            ) as nova:
                    
                    # Set custom HTTP headers if configured
                    if execution_headers and execution_headers.headers:
                        logger.info(f"Setting {len(execution_headers.headers)} custom HTTP headers")
                        parsed_headers = {}
                        for header_name, header_value in execution_headers.headers.items():
                            parsed_value = template_parser.parse_instruction(header_value)
                            parsed_headers[header_name] = parsed_value
                        nova.page.set_extra_http_headers(parsed_headers)
                        nova.go_to_url(execution.starting_url)
                    
                    logger.info("NovaAct initialized successfully")
                    
                    # Get session ID and update execution
                    session_id_nova = nova.get_session_id()
                    logger.info(f"Nova Act session ID: {session_id_nova}")
                    db_client.update_execution_session_id(usecase_id, session_id, session_id_nova)
                    
                    # Update last activity
                    last_activity = time.time()
                    db_client.update_execution_last_activity(usecase_id, session_id, get_time())
                    
                    # Main command loop
                    logger.info("Entering command loop...")
                    use_eventbridge = os.getenv('USE_EVENTBRIDGE_COMMANDS', 'true').lower() == 'true'
                    logger.info(f"Command mode: {'EventBridge/DynamoDB' if use_eventbridge else 'SQS'}")
                    
                    while True:
                        # Check for inactivity timeout
                        if time.time() - last_activity > INACTIVITY_TIMEOUT:
                            logger.info("Inactivity timeout reached, terminating session")
                            db_client.update_execution_status(usecase_id, session_id, "timeout", completed_at=get_time())
                            break
                        
                        try:
                            command = None
                            
                            if use_eventbridge:
                                # Poll DynamoDB for commands (EventBridge mode)
                                commands = db_client.poll_wizard_commands(session_id, limit=1)
                                
                                if not commands:
                                    # No commands, sleep briefly and continue
                                    time.sleep(1)
                                    continue
                                
                                command_record = commands[0]
                                command = {
                                    'action': command_record.get('action'),
                                    'sessionId': command_record.get('sessionId') or command_record.get('session_id'),
                                    'stepId': command_record.get('stepId') or command_record.get('step_id'),
                                    'step_id': command_record.get('stepId') or command_record.get('step_id')  # For compatibility
                                }
                                
                                logger.info(f"Received command from DynamoDB for session {session_id}")
                                logger.info(f"Command details: {json.dumps(command, indent=2)}")
                                logger.info(f"Full command record: {json.dumps(command_record, indent=2, default=str)}")
                                
                                # Delete command from DynamoDB after reading
                                db_client.delete_wizard_command(session_id, command_record['sk'])
                                
                                last_activity = time.time()
                                db_client.update_execution_last_activity(usecase_id, session_id, get_time())
                                
                            else:
                                # Poll SQS for commands (legacy mode)
                                response = sqs_client.receive_message(
                                    QueueUrl=wizard_queue_url,
                                    MaxNumberOfMessages=1,
                                    WaitTimeSeconds=20,
                                    MessageAttributeNames=['All']
                                )
                                
                                if 'Messages' not in response:
                                    continue
                                
                                message = response['Messages'][0]
                                command = json.loads(message['Body'])
                                command_session_id = command.get('session_id') or command.get('SessionID')
                                
                                # Validate this message is for our session
                                if command_session_id != session_id:
                                    logger.warning(f"Ignoring command for different session: {command_session_id} (ours: {session_id})")
                                    continue
                                
                                logger.info(f"Received command from SQS for session {session_id}")
                                logger.info(f"Command details: {json.dumps(command, indent=2)}")
                                
                                # Delete message from queue
                                sqs_client.delete_message(
                                    QueueUrl=wizard_queue_url,
                                    ReceiptHandle=message['ReceiptHandle']
                                )
                                
                                last_activity = time.time()
                                db_client.update_execution_last_activity(usecase_id, session_id, get_time())
                            
                            # Process command (unified for both modes)
                            if not command:
                                continue
                            
                            logger.info(f"Processing command: {command['action']}")
                            
                            if command['action'] == 'execute_step':
                                # Get step from DynamoDB
                                step_id = command['step_id']
                                step = db_client.get_execution_step(session_id, step_id)
                                
                                if step:
                                    act_id, status, success, logs, actual_value = execute_single_step(
                                        nova, step, template_parser, usecase_id, session_id, s3_bucket_name, db_client
                                    )
                                    
                                    # Update step status
                                    db_client.update_execution_step_status(
                                        session_id, step_id, act_id, status, logs, actual_value
                                    )
                                else:
                                    logger.error(f"Step {step_id} not found")
                            
                            elif command['action'] == 'restart':
                                logger.info("Restarting wizard session...")
                                # Close current browser
                                nova.close()
                                browser.stop()
                                delete_browser(browser_id, execution.region)
                                
                                # Create new browser
                                browser_id = create_browser(
                                    template_parser.get_all_variables()['UniqueID'],
                                    session_id,
                                    s3_bucket_name,
                                    f"{usecase_id}/{session_id}/recording/",
                                    execution.region
                                )
                                browser = start_browser(browser_id, session_id, execution.region)
                                ws_url, headers = browser.generate_ws_headers()
                                live_view_url = browser.generate_live_view_url()
                                db_client.create_live_view(session_id, live_view_url)
                                
                                # Reinitialize NovaAct (Preview API mode)
                                nova = NovaAct(
                                    cdp_endpoint_url=ws_url,
                                    cdp_headers=headers,
                                    starting_page=execution.starting_url,
                                    headless=execution.headless,
                                    logs_directory=execution_logs_dir,
                                    ignore_https_errors=True,
                                    chrome_channel="chromium",
                                    stop_hooks=[s3_writer],
                                    nova_act_api_key=nova_api_key,
                                    user_agent=os.getenv('USER_AGENT', 'Mozilla/5.0')
                                )
                                nova.__enter__()
                                
                                # Replay accepted steps
                                accepted_steps = db_client.get_accepted_execution_steps(session_id)
                                logger.info(f"Replaying {len(accepted_steps)} accepted steps")
                                
                                for step in accepted_steps:
                                    act_id, status, success, logs, actual_value = execute_single_step(
                                        nova, step, template_parser, usecase_id, session_id, s3_bucket_name, db_client
                                    )
                                    if not success:
                                        logger.error(f"Failed to replay step {step.sort}")
                                        break
                                
                                logger.info("Restart complete")
                            
                            elif command['action'] == 'terminate':
                                logger.info("Terminating wizard session - starting graceful shutdown")
                                
                                # Update execution status to success (wizard completed successfully)
                                db_client.update_execution_status(usecase_id, session_id, "success", completed_at=get_time())
                                
                                # Close browser gracefully
                                try:
                                    logger.info("Closing NovaAct session...")
                                    nova.close()
                                except Exception as close_err:
                                    logger.error(f"Error closing NovaAct: {close_err}")
                                
                                # Stop browser
                                try:
                                    logger.info("Stopping browser...")
                                    browser.stop()
                                except Exception as stop_err:
                                    logger.error(f"Error stopping browser: {stop_err}")
                                
                                # Delete browser
                                try:
                                    logger.info("Deleting browser...")
                                    delete_browser(browser_id, execution.region)
                                except Exception as delete_err:
                                    logger.error(f"Error deleting browser: {delete_err}")
                                
                                # Delete live view
                                try:
                                    logger.info("Deleting live view...")
                                    db_client.delete_live_view(session_id)
                                except Exception as lv_err:
                                    logger.error(f"Error deleting live view: {lv_err}")
                                
                                logger.info("Graceful shutdown complete - exiting")
                                break
                        
                        except Exception as e:
                            logger.error(f"Error in command loop: {e}")
                            continue
    
    except Exception as e:
        logger.error(f"Wizard worker failed: {e}")
        db_client.update_execution_status(usecase_id, session_id, "failed", completed_at=get_time())
        return False
    
    finally:
        # Final cleanup (in case terminate wasn't called or there was an error)
        logger.info("Running final cleanup...")
        try:
            if 'nova' in locals():
                try:
                    nova.close()
                except:
                    pass
            
            if 'browser' in locals():
                try:
                    browser.stop()
                except:
                    pass
            
            if 'browser_id' in locals() and 'execution' in locals():
                try:
                    delete_browser(browser_id, execution.region)
                except:
                    pass
            
            if 'session_id' in locals():
                try:
                    db_client.delete_live_view(session_id)
                except:
                    pass
        except Exception as cleanup_error:
            logger.error(f"Final cleanup error: {cleanup_error}")
    
    logger.info(f"Wizard session {session_id} completed")
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
