import os
import re
import logging
from typing import Any, Dict
import boto3
from utils import create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get a schedule for a use case from Amazon EventBridge Scheduler.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with schedule information
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/usecases.read'])
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
        
        # Initialize Amazon EventBridge Scheduler client
        scheduler_client = boto3.client('scheduler')
        
        # Get the schedule
        try:
            response = scheduler_client.get_schedule(
                Name=usecase_id,
                GroupName=scheduler_group_name
            )
        except scheduler_client.exceptions.ResourceNotFoundException:
            return create_response(404, {'error': 'Schedule not found'})
        
        # Parse rate expression to extract rate and unit
        # Format: rate(5 minutes) or rate(1 hour)
        schedule_expression = response.get('ScheduleExpression', '')
        rate_match = re.match(r'rate\((\d+)\s+(\w+)\)', schedule_expression)
        
        rate = 0
        unit = ''
        if rate_match:
            rate = int(rate_match.group(1))
            unit = rate_match.group(2)
        
        # Check if schedule is enabled
        enabled = response.get('State') == 'ENABLED'
        
        return create_response(200, {
            'rate': rate,
            'unit': unit,
            'enabled': enabled
        })
        
    except Exception as e:
        logger.error(f"Error getting schedule: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
