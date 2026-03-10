import logging
import json
from typing import Any, Dict
from uuid import uuid4
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, get_current_timestamp, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to accept a wizard step and make it permanent.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with acceptance result
    """
    # Validate scopes - accepting wizard steps modifies usecases
    user_identity, error = require_scopes(event, ['api/usecases.write'])
    if error:
        return error
    
    try:
        # Get parameters from path
        session_id, error = validate_path_id(event.get('pathParameters', {}).get('sessionId'), 'session ID')
        if error:
            return error
        step_id, error = validate_path_id(event.get('pathParameters', {}).get('stepId'), 'step ID')
        if error:
            return error
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('usecaseId'), 'usecase ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get the execution step
        response = table.get_item(
            Key={
                'pk': f'EXECUTION#{session_id}',
                'sk': f'EXECUTION_STEP#{step_id}'
            }
        )
        
        if 'Item' not in response:
            return create_response(404, {'error': 'Step not found'})
        
        execution_step = response['Item']
        
        # Count existing accepted steps to determine sort order
        query_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'EXECUTION#{session_id}') & Key('sk').begins_with('EXECUTION_STEP#'),
            FilterExpression='acceptance_status = :status',
            ExpressionAttributeValues={
                ':status': 'accepted'
            }
        )
        
        next_sort = len(query_response.get('Items', []))
        
        # Update execution step to accepted
        table.update_item(
            Key={
                'pk': f'EXECUTION#{session_id}',
                'sk': f'EXECUTION_STEP#{step_id}'
            },
            UpdateExpression='SET acceptance_status = :status, #temp = :temp, sort = :sort',
            ExpressionAttributeNames={
                '#temp': 'temporary'
            },
            ExpressionAttributeValues={
                ':status': 'accepted',
                ':temp': False,
                ':sort': next_sort
            }
        )
        
        # Create permanent step in usecase
        permanent_step_id = str(uuid4())
        now = get_current_timestamp()
        
        permanent_step = {
            'pk': f'USECASE#{usecase_id}',
            'sk': f'STEP#{permanent_step_id}',
            'id': permanent_step_id,
            'sort': next_sort,
            'instruction': execution_step.get('instruction', ''),
            'step_type': execution_step.get('step_type', ''),
            'created_at': now
        }
        
        # Copy optional fields
        optional_fields = [
            'secret_key', 'validation_type', 'validation_operator',
            'validation_value', 'capture_variable', 'assertion_variable', 'value_type'
        ]
        for field in optional_fields:
            if field in execution_step:
                permanent_step[field] = execution_step[field]
        
        # Save permanent step
        table.put_item(Item=permanent_step)
        
        logger.info(f"Accepted wizard step {step_id} and created permanent step {permanent_step_id}")
        
        return create_response(200, {
            'status': 'accepted',
            'step_id': permanent_step_id
        })
        
    except Exception as e:
        logger.error(f"Error accepting wizard step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
