import logging
import os
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, get_current_timestamp

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to stop a running execution by stopping its ECS task.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with stop confirmation
    """
    try:
        # Get parameters from path
        path_params = event.get('pathParameters', {})
        execution_id = path_params.get('executionId')
        usecase_id = path_params.get('id')
        
        if not execution_id or not usecase_id:
            return create_response(400, {'error': 'missing executionId or usecaseId'})
        
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Load execution to get task ARN
        response = table.get_item(
            Key={
                'pk': f'USECASE_EXECUTION#{usecase_id}',
                'sk': f'EXECUTION#{execution_id}'
            }
        )
        
        if 'Item' not in response:
            return create_response(404, {'error': 'execution not found'})
        
        execution = response['Item']
        
        # Check if execution has a task ARN
        task_arn = execution.get('task_arn', '')
        if not task_arn:
            return create_response(400, {'error': 'execution has no associated ECS task'})
        
        # Check if execution is already in a terminal state
        status = execution.get('status', '')
        if status in ['success', 'failed', 'stopped', 'error']:
            return create_response(400, {'error': f'execution is already in terminal state: {status}'})
        
        # Stop the ECS task
        ecs_client = boto3.client('ecs')
        cluster_arn = os.environ.get('ECS_CLUSTER')
        
        logger.info(f"Stopping ECS task: {task_arn} in cluster: {cluster_arn}")
        
        try:
            ecs_client.stop_task(
                cluster=cluster_arn,
                task=task_arn,
                reason='User requested stop via API'
            )
            logger.info(f"Successfully stopped ECS task: {task_arn}")
        except ClientError as e:
            # Don't fail completely - update status anyway
            # The task might already be stopped or not exist
            logger.warning(f"Failed to stop task, but will update execution status anyway: {str(e)}")
        
        # Update execution status to stopped
        completed_at = get_current_timestamp()
        table.update_item(
            Key={
                'pk': f'USECASE_EXECUTION#{usecase_id}',
                'sk': f'EXECUTION#{execution_id}'
            },
            UpdateExpression='SET #status = :status, completed_at = :completed_at',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'stopped',
                ':completed_at': completed_at
            }
        )
        
        logger.info(f"Updated execution {execution_id} status to stopped")
        
        return create_response(200, {
            'status': 'stopped',
            'executionId': execution_id,
            'taskArn': task_arn,
            'stoppedAt': completed_at
        })
        
    except Exception as e:
        logger.error(f"Error stopping execution: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
