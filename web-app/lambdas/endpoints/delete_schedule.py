import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a schedule for a use case from EventBridge Scheduler.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/usecases.write'])
        if error:
            return error
        
        # Get use case ID from path parameters
        usecase_id = event.get('pathParameters', {}).get('id')
        if not usecase_id:
            return create_response(400, {'error': 'Missing use case ID'})
        
        # Get scheduler group name from environment
        scheduler_group_name = os.environ.get('SCHEDULER_GROUP_NAME')
        if not scheduler_group_name:
            logger.error("SCHEDULER_GROUP_NAME environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize EventBridge Scheduler client
        scheduler_client = boto3.client('scheduler')
        
        # Delete the schedule
        scheduler_client.delete_schedule(
            Name=usecase_id,
            GroupName=scheduler_group_name
        )
        
        return create_response(200, {'status': 'schedule deleted'})
        
    except Exception as e:
        logger.error(f"Error deleting schedule: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
