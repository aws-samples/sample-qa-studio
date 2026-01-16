import logging
from typing import Any, Dict, Optional, Tuple, List
import boto3
from utils import get_table_name, get_current_timestamp

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
