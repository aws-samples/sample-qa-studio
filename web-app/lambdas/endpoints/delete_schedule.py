import os
import logging
from typing import Any, Dict
import boto3
from utils import no_content_response, create_response
from resource_auth import require_resource_access, usecase_from_path

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a schedule for a use case from Amazon EventBridge Scheduler.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Get use case ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by the resolver
        
        # Get scheduler group name from environment
        scheduler_group_name = os.environ.get('SCHEDULER_GROUP_NAME')
        if not scheduler_group_name:
            logger.error("SCHEDULER_GROUP_NAME environment variable not set")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize Amazon EventBridge Scheduler client
        scheduler_client = boto3.client('scheduler')
        
        # Delete the schedule
        scheduler_client.delete_schedule(
            Name=usecase_id,
            GroupName=scheduler_group_name
        )
        
        return no_content_response()
        
    except Exception as e:
        logger.error(f"Error deleting schedule: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
