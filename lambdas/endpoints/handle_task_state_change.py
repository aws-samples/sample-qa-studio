import logging
from typing import Any, Dict, Optional, Tuple, List
import boto3

from utils import get_table_name, get_current_timestamp
from test_suite_schema import (
    get_suite_exec_result_pk,
    get_result_sk,
    get_suite_execution_pk,
    get_execution_sk
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> None:
    """
    Lambda handler for ECS task state change events from EventBridge.
    Monitors ECS task failures and updates execution status in DynamoDB.
    
    Args:
        event: CloudWatch/EventBridge event
        context: Lambda context
    """
    try:
        logger.info(f"Received ECS task state change event: {event.get('detail-type')}")
        
        # Parse the event detail
        detail = event.get('detail', {})
        
        # Only process STOPPED tasks
        last_status = detail.get('lastStatus', '')
        if last_status != 'STOPPED':
            logger.info(f"Task status is {last_status}, not STOPPED. Ignoring.")
            return
        
        task_arn = detail.get('taskArn', '')
        stopped_reason = detail.get('stoppedReason', '')
        stop_code = detail.get('stopCode', '')
        
        logger.info(f"Processing STOPPED task: {task_arn}")
        logger.info(f"Stop reason: {stopped_reason}")
        logger.info(f"Stop code: {stop_code}")
        
        # Extract task ID from ARN
        task_id = extract_task_id(task_arn)
        if not task_id:
            logger.warning(f"Could not extract task ID from ARN: {task_arn}")
            return
        
        # Initialize DynamoDB
        dynamodb_client = boto3.client('dynamodb')
        table_name = get_table_name()
        
        # Find the execution associated with this task
        execution, usecase_id, execution_id = find_execution_by_task_arn(
            dynamodb_client, table_name, task_arn
        )
        
        if not execution:
            logger.info(f"No execution found for task ARN: {task_arn}")
            return
        
        logger.info(f"Found execution: {execution_id} for usecase: {usecase_id}")
        
        # Check if execution is already in a terminal state
        status = execution.get('status', {}).get('S', '')
        if status in ['success', 'failed', 'stopped', 'error']:
            logger.info(f"Execution already in terminal state: {status}. Skipping update.")
            return
        
        # Determine if this is a failure and get error message
        is_failure, error_message = analyze_task_failure(detail)
        
        if is_failure:
            logger.info(f"Task failed: {error_message}")
            
            # Update execution status to failed
            completed_at = get_current_timestamp()
            
            try:
                dynamodb_client.update_item(
                    TableName=table_name,
                    Key={
                        'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                        'sk': {'S': f'EXECUTION#{execution_id}'}
                    },
                    UpdateExpression='SET #status = :status, completed_at = :completed_at, error_message = :error_msg',
                    ExpressionAttributeNames={
                        '#status': 'status'
                    },
                    ExpressionAttributeValues={
                        ':status': {'S': 'failed'},
                        ':completed_at': {'S': completed_at},
                        ':error_msg': {'S': error_message}
                    }
                )
                logger.info(f"Updated execution {execution_id} to failed status")
                
                # Update suite execution tracking if this execution is part of a suite
                update_suite_execution_tracking(
                    dynamodb_client, table_name, execution_id, usecase_id, 'failed', 
                    completed_at, error_message
                )
                
            except Exception as e:
                logger.error(f"Error updating execution status: {str(e)}")
                raise
        else:
            logger.info("Task stopped normally (user requested or successful completion)")
    
    except Exception as e:
        logger.error(f"Error processing task state change: {str(e)}", exc_info=True)
        # Don't raise - we don't want EventBridge to retry


def extract_task_id(task_arn: str) -> str:
    """
    Extract the task ID from the task ARN.
    Task ARN format: arn:aws:ecs:region:account:task/cluster-name/task-id
    
    Args:
        task_arn: The ECS task ARN
        
    Returns:
        The task ID or empty string if extraction fails
    """
    parts = task_arn.split('/')
    if parts:
        return parts[-1]
    return ''


def find_execution_by_task_arn(
    client: Any, 
    table_name: str, 
    task_arn: str
) -> Tuple[Optional[Dict], str, str]:
    """
    Find an execution by its task ARN using DynamoDB scan.
    
    Note: This uses a scan operation which is not ideal for performance.
    In production, consider using a GSI on task_arn for better performance.
    
    Args:
        client: Boto3 DynamoDB client
        table_name: DynamoDB table name
        task_arn: The ECS task ARN to search for
        
    Returns:
        Tuple of (execution dict, usecase_id, execution_id) or (None, '', '') if not found
    """
    logger.info(f"Scanning for execution with task ARN: {task_arn}")
    
    try:
        response = client.scan(
            TableName=table_name,
            FilterExpression='task_arn = :task_arn AND begins_with(pk, :pk_prefix)',
            ExpressionAttributeValues={
                ':task_arn': {'S': task_arn},
                ':pk_prefix': {'S': 'USECASE_EXECUTION#'}
            }
        )
        
        items = response.get('Items', [])
        if not items:
            return None, '', ''
        
        # Parse the first matching execution
        execution = items[0]
        
        # Extract usecase ID and execution ID from the keys
        pk = execution.get('pk', {}).get('S', '')
        sk = execution.get('sk', {}).get('S', '')
        
        usecase_id = pk.replace('USECASE_EXECUTION#', '')
        execution_id = sk.replace('EXECUTION#', '')
        
        return execution, usecase_id, execution_id
        
    except Exception as e:
        logger.error(f"Error scanning for execution: {str(e)}")
        raise


def analyze_task_failure(detail: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Determine if the task stopped due to a failure and return an error message.
    
    Args:
        detail: The ECS task state change detail from EventBridge
        
    Returns:
        Tuple of (is_failure: bool, error_message: str)
    """
    stop_code = detail.get('stopCode', '')
    stopped_reason = detail.get('stoppedReason', '')
    containers = detail.get('containers', [])
    
    # Check stop code - TaskFailedToStart indicates infrastructure issues
    if stop_code == 'TaskFailedToStart':
        return True, f"Task failed to start: {stopped_reason}"
    
    # Check if stopped reason indicates a failure
    stopped_reason_lower = stopped_reason.lower()
    
    # Common failure patterns
    failure_patterns = [
        'cannotpullcontainererror',
        'resourceinitializationerror',
        'outofmemoryerror',
        'essential container',
        'failed',
        'error'
    ]
    
    for pattern in failure_patterns:
        if pattern in stopped_reason_lower:
            return True, f"Task stopped due to error: {stopped_reason}"
    
    # Check container exit codes
    for container in containers:
        exit_code = container.get('exitCode')
        container_name = container.get('name', 'unknown')
        container_reason = container.get('reason', '')
        
        if exit_code is not None and exit_code != 0:
            reason = container_reason if container_reason else f"Container exited with code {exit_code}"
            return True, f"Container '{container_name}' failed: {reason}"
        
        # Check for container-level failures
        if container_reason:
            container_reason_lower = container_reason.lower()
            for pattern in failure_patterns:
                if pattern in container_reason_lower:
                    return True, f"Container '{container_name}' failed: {container_reason}"
    
    # If stopped reason is "User requested stop" or similar, it's not a failure
    if 'user' in stopped_reason_lower or 'scaling' in stopped_reason_lower:
        return False, ''
    
    # If we can't determine, assume it's not a failure (worker might have updated status already)
    return False, ''


def update_suite_execution_tracking(
    client: Any,
    table_name: str,
    usecase_execution_id: str,
    usecase_id: str,
    status: str,
    completed_at: str,
    error_message: Optional[str] = None
) -> None:
    """
    Update suite execution tracking when a use case execution completes.
    
    This function:
    1. Checks if execution is part of a suite (has suite_execution_id)
    2. Updates suite execution counters atomically
    3. Checks if the suite execution is complete and updates status
    4. Updates test suite summary when complete
    
    Args:
        client: Boto3 DynamoDB client
        table_name: DynamoDB table name
        usecase_execution_id: The use case execution ID that completed
        usecase_id: The use case ID
        status: Final status ('success', 'failed', 'stopped', 'error')
        completed_at: Completion timestamp
        error_message: Optional error message if failed
    """
    logger.info(f"Updating suite execution tracking for usecase_execution_id: {usecase_execution_id}")
    
    try:
        # Get the execution to check for suite_execution_id
        exec_response = client.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{usecase_execution_id}'}
            }
        )
        
        if 'Item' not in exec_response:
            logger.warning(f"Execution {usecase_execution_id} not found")
            return
        
        execution = exec_response['Item']
        
        # Check if this execution has a suite_execution_id
        suite_execution_id_attr = execution.get('suite_execution_id', {})
        suite_execution_id = suite_execution_id_attr.get('S') if suite_execution_id_attr else None
        
        if not suite_execution_id:
            logger.info(f"Execution {usecase_execution_id} is not part of a suite execution")
            return
        
        logger.info(f"Found suite_execution_id: {suite_execution_id}")
        
        # Find the suite execution record to get suite_id
        suite_exec_response = client.scan(
            TableName=table_name,
            FilterExpression='id = :exec_id AND begins_with(pk, :pk_prefix)',
            ExpressionAttributeValues={
                ':exec_id': {'S': suite_execution_id},
                ':pk_prefix': {'S': 'SUITE_EXECUTION#'}
            },
            Limit=1
        )
        
        suite_exec_items = suite_exec_response.get('Items', [])
        if not suite_exec_items:
            logger.warning(f"Suite execution {suite_execution_id} not found")
            return
        
        suite_id = suite_exec_items[0].get('suite_id', {}).get('S', '')
        if not suite_id:
            logger.warning(f"Missing suite_id in suite execution {suite_execution_id}")
            return
        
        logger.info(f"Processing suite execution: suite_id={suite_id}, suite_execution_id={suite_execution_id}")
        
        # Update suite execution counters
        update_suite_execution_counters(
            client, table_name, suite_id, suite_execution_id, status
        )
        
        # Check if suite execution is complete and update test suite summary
        check_suite_completion(
            client, table_name, suite_id, suite_execution_id
        )
        
        logger.info(f"Completed suite execution tracking updates")
        
    except Exception as e:
        logger.error(f"Error in suite execution tracking: {str(e)}", exc_info=True)
        # Don't raise - we don't want to fail the main handler


def query_suite_execution_results(
    client: Any,
    table_name: str,
    usecase_execution_id: str
) -> List[Dict[str, Any]]:
    """
    Find all suite execution results that contain a specific use case execution.
    
    This function:
    1. Gets the execution record to find suite_execution_id
    2. If suite_execution_id exists, finds the suite execution result
    
    Args:
        client: Boto3 DynamoDB client
        table_name: DynamoDB table name
        usecase_execution_id: The use case execution ID to search for
        
    Returns:
        List of suite execution result items
    """
    logger.info(f"Querying suite execution results for usecase_execution_id: {usecase_execution_id}")
    
    try:
        # Scan for the execution to get suite_execution_id and usecase_id
        exec_response = client.scan(
            TableName=table_name,
            FilterExpression='begins_with(sk, :sk_prefix)',
            ExpressionAttributeValues={
                ':sk_prefix': {'S': f'EXECUTION#{usecase_execution_id}'}
            },
            Limit=1
        )
        
        exec_items = exec_response.get('Items', [])
        if not exec_items:
            logger.info(f"Execution {usecase_execution_id} not found")
            return []
        
        execution = exec_items[0]
        
        # Check if this execution has a suite_execution_id
        suite_execution_id = execution.get('suite_execution_id', {}).get('S')
        if not suite_execution_id:
            logger.info(f"Execution {usecase_execution_id} is not part of a suite execution")
            return []
        
        # Extract usecase_id from pk (format: USECASE_EXECUTION#{usecase_id})
        pk = execution.get('pk', {}).get('S', '')
        if not pk.startswith('USECASE_EXECUTION#'):
            logger.warning(f"Unexpected pk format: {pk}")
            return []
        
        usecase_id = pk.replace('USECASE_EXECUTION#', '')
        logger.info(f"Found suite_execution_id: {suite_execution_id}, usecase_id: {usecase_id}")
        
        # Find the suite execution result for this suite_execution_id and usecase_id
        suite_results_response = client.scan(
            TableName=table_name,
            FilterExpression='suite_execution_id = :suite_exec_id AND usecase_id = :usecase_id AND begins_with(pk, :pk_prefix)',
            ExpressionAttributeValues={
                ':suite_exec_id': {'S': suite_execution_id},
                ':usecase_id': {'S': usecase_id},
                ':pk_prefix': {'S': 'SUITE_EXEC#'}
            }
        )
        
        suite_results = suite_results_response.get('Items', [])
        logger.info(f"Found {len(suite_results)} suite execution results")
        
        return suite_results
        
    except Exception as e:
        logger.error(f"Error querying suite execution results: {str(e)}")
        # Don't raise - we want to continue processing even if suite updates fail
        return []


def update_suite_execution_result(
    client: Any,
    table_name: str,
    suite_execution_id: str,
    usecase_id: str,
    status: str,
    completed_at: str,
    error_message: Optional[str] = None,
    usecase_execution_id: Optional[str] = None
) -> bool:
    """
    Update the status of a specific suite execution result.
    
    Args:
        client: Boto3 DynamoDB client
        table_name: DynamoDB table name
        suite_execution_id: The suite execution ID
        usecase_id: The use case ID
        status: New status ('success', 'failed', 'stopped', etc.)
        completed_at: Completion timestamp
        error_message: Optional error message if failed
        usecase_execution_id: Optional use case execution ID for linking
        
    Returns:
        True if update succeeded, False otherwise
    """
    logger.info(f"Updating suite execution result: suite={suite_execution_id}, usecase={usecase_id}, status={status}")
    
    try:
        update_expr = 'SET #status = :status, completed_at = :completed_at'
        expr_attr_names = {'#status': 'status'}
        expr_attr_values = {
            ':status': {'S': status},
            ':completed_at': {'S': completed_at}
        }
        
        if error_message:
            update_expr += ', error_message = :error_msg'
            expr_attr_values[':error_msg'] = {'S': error_message}
        
        if usecase_execution_id:
            update_expr += ', usecase_execution_id = :usecase_execution_id'
            expr_attr_values[':usecase_execution_id'] = {'S': usecase_execution_id}
        
        client.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': get_suite_exec_result_pk(suite_execution_id)},
                'sk': {'S': get_result_sk(usecase_id)}
            },
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
        
        logger.info(f"Successfully updated suite execution result for usecase {usecase_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating suite execution result: {str(e)}")
        return False


def update_suite_execution_counters(
    client: Any,
    table_name: str,
    suite_id: str,
    suite_execution_id: str,
    status: str
) -> bool:
    """
    Update suite execution counters atomically based on use case status.
    
    When a use case execution completes:
    - Increment completed_usecases
    - Decrement running_usecases
    - Increment successful_usecases (if success) or failed_usecases (if failed/stopped)
    
    Args:
        client: Boto3 DynamoDB client
        table_name: DynamoDB table name
        suite_id: The test suite ID
        suite_execution_id: The suite execution ID
        status: The final status of the use case ('success', 'failed', 'stopped', 'error')
        
    Returns:
        True if update succeeded, False otherwise
    """
    logger.info(f"Updating suite execution counters: suite_execution={suite_execution_id}, status={status}")
    
    try:
        # Determine which counters to update based on status
        if status == 'success':
            update_expr = 'ADD completed_usecases :inc, successful_usecases :inc, running_usecases :dec'
            expr_attr_values = {
                ':inc': {'N': '1'},
                ':dec': {'N': '-1'}
            }
        elif status in ['failed', 'stopped', 'error']:
            # Treat 'stopped' status as 'failed' for suite execution counter purposes
            update_expr = 'ADD completed_usecases :inc, failed_usecases :inc, running_usecases :dec'
            expr_attr_values = {
                ':inc': {'N': '1'},
                ':dec': {'N': '-1'}
            }
        else:
            logger.warning(f"Unknown status '{status}' for counter update, skipping")
            return False
        
        client.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': get_suite_execution_pk(suite_id)},
                'sk': {'S': get_execution_sk(suite_execution_id)}
            },
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_attr_values
        )
        
        logger.info(f"Successfully updated suite execution counters")
        return True
        
    except Exception as e:
        logger.error(f"Error updating suite execution counters: {str(e)}")
        return False


def check_suite_completion(
    client: Any,
    table_name: str,
    suite_id: str,
    suite_execution_id: str
) -> bool:
    """
    Check if all use cases in a suite execution are complete and update suite status.
    
    Determines final suite status:
    - 'completed': All use cases succeeded
    - 'partial': Some use cases failed but at least one succeeded
    - 'failed': All use cases failed
    
    Args:
        client: Boto3 DynamoDB client
        table_name: DynamoDB table name
        suite_id: The test suite ID
        suite_execution_id: The suite execution ID
        
    Returns:
        True if suite is complete and was updated, False otherwise
    """
    logger.info(f"Checking suite completion: suite_execution={suite_execution_id}")
    
    try:
        # Get current suite execution state
        response = client.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': get_suite_execution_pk(suite_id)},
                'sk': {'S': get_execution_sk(suite_execution_id)}
            }
        )
        
        if 'Item' not in response:
            logger.warning(f"Suite execution {suite_execution_id} not found")
            return False
        
        suite_execution = response['Item']
        
        # Extract counters
        total_usecases = int(suite_execution.get('total_usecases', {}).get('N', '0'))
        completed_usecases = int(suite_execution.get('completed_usecases', {}).get('N', '0'))
        successful_usecases = int(suite_execution.get('successful_usecases', {}).get('N', '0'))
        failed_usecases = int(suite_execution.get('failed_usecases', {}).get('N', '0'))
        
        logger.info(f"Suite execution counters: total={total_usecases}, completed={completed_usecases}, "
                   f"successful={successful_usecases}, failed={failed_usecases}")
        
        # Check if all use cases are complete
        if completed_usecases < total_usecases:
            logger.info(f"Suite execution not yet complete: {completed_usecases}/{total_usecases}")
            return False
        
        # Determine final status
        if failed_usecases == 0:
            final_status = 'completed'
        elif successful_usecases == 0:
            final_status = 'failed'
        else:
            final_status = 'partial'
        
        completed_at = get_current_timestamp()
        
        logger.info(f"Suite execution complete with status: {final_status}")
        
        # Calculate duration
        started_at_str = suite_execution.get('started_at', {}).get('S', '')
        duration_seconds = 0
        if started_at_str:
            try:
                from datetime import datetime
                started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                completed_at_dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                duration_seconds = int((completed_at_dt - started_at).total_seconds())
            except Exception as e:
                logger.warning(f"Could not calculate duration: {str(e)}")
        
        # Update suite execution status
        update_expr = 'SET #status = :status, completed_at = :completed_at'
        expr_attr_values = {
            ':status': {'S': final_status},
            ':completed_at': {'S': completed_at}
        }
        
        if duration_seconds > 0:
            update_expr += ', duration_seconds = :duration'
            expr_attr_values[':duration'] = {'N': str(duration_seconds)}
        
        client.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': get_suite_execution_pk(suite_id)},
                'sk': {'S': get_execution_sk(suite_execution_id)}
            },
            UpdateExpression=update_expr,
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues=expr_attr_values
        )
        
        logger.info(f"Updated suite execution {suite_execution_id} to status: {final_status}")
        
        # Update test suite summary with last execution info
        update_test_suite_summary(client, table_name, suite_id, final_status, successful_usecases, failed_usecases, total_usecases)
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking suite completion: {str(e)}")
        return False


def update_test_suite_summary(
    client: Any,
    table_name: str,
    suite_id: str,
    last_status: str,
    successful: int,
    failed: int,
    total: int
) -> bool:
    """
    Update the test suite record with last execution summary.
    
    Args:
        client: Boto3 DynamoDB client
        table_name: DynamoDB table name
        suite_id: The test suite ID
        last_status: Last execution status
        successful: Number of successful use cases
        failed: Number of failed use cases
        total: Total number of use cases
        
    Returns:
        True if update succeeded, False otherwise
    """
    from utils import get_current_timestamp
    
    logger.info(f"Updating test suite {suite_id} summary: status={last_status}, {successful}/{total} successful")
    
    try:
        client.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': 'TEST_SUITES'},
                'sk': {'S': f'SUITE#{suite_id}'}
            },
            UpdateExpression='SET last_execution_status = :status, last_successful_count = :successful, last_failed_count = :failed, last_execution_time = :time',
            ExpressionAttributeValues={
                ':status': {'S': last_status},
                ':successful': {'N': str(successful)},
                ':failed': {'N': str(failed)},
                ':time': {'S': get_current_timestamp()}
            }
        )
        
        logger.info(f"Updated test suite {suite_id} summary")
        return True
        
    except Exception as e:
        logger.error(f"Error updating test suite summary: {str(e)}")
        return False
