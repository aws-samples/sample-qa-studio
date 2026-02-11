import json
import os
import logging
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from utils import create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a schedule for a use case in EventBridge Scheduler.
    
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
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        rate = body.get('rate')
        unit = body.get('unit')
        
        if not rate or not unit:
            return create_response(400, {'error': 'Rate and unit are required'})
        
        # Get environment variables
        scheduler_group_name = os.environ.get('SCHEDULER_GROUP_NAME')
        execute_usecase_lambda_arn = os.environ.get('EXECUTE_USECASE_LAMBDA_ARN')
        scheduler_target_role_arn = os.environ.get('SCHEDULER_TARGET_ROLE_ARN')
        
        if not all([scheduler_group_name, execute_usecase_lambda_arn, scheduler_target_role_arn]):
            logger.error("Missing required environment variables")
            return create_response(500, {'error': 'Internal server error'})
        
        # Initialize EventBridge Scheduler client
        scheduler_client = boto3.client('scheduler')
        
        # Delete existing schedule if it exists
        try:
            scheduler_client.delete_schedule(
                Name=usecase_id,
                GroupName=scheduler_group_name
            )
            logger.info(f"Deleted existing schedule for usecase {usecase_id}")
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                logger.warning(f"Error deleting existing schedule: {str(e)}")
        
        # Create rate expression
        rate_expression = f"rate({rate} {unit})"
        
        # Create the schedule
        scheduler_client.create_schedule(
            Name=usecase_id,
            GroupName=scheduler_group_name,
            ScheduleExpression=rate_expression,
            Target={
                'Arn': execute_usecase_lambda_arn,
                'RoleArn': scheduler_target_role_arn,
                'Input': json.dumps({
                    'pathParameters': {'id': usecase_id},
                    'queryStringParameters': {'trigger-type': 'Scheduled'}
                })
            },
            FlexibleTimeWindow={
                'Mode': 'OFF'
            }
        )
        
        return create_response(201, {
            'status': 'schedule created',
            'rate': rate,
            'unit': unit
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating schedule: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
