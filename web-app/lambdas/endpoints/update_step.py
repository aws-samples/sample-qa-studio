import json
import logging
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update a step in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Validate scopes
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        # Get usecase ID and step ID from path parameters
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error

        step_id, error = validate_path_id(event.get('pathParameters', {}).get('stepId'), 'step ID')
        if error:
            return error
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        instruction = body.get('instruction')
        step_type = body.get('step_type')
        
        if not instruction or not step_type:
            return create_response(400, {'error': 'Instruction and step_type are required'})
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Build dynamic update expression
        update_expression_parts = ['instruction = :instruction', 'step_type = :step_type']
        expression_attribute_values = {
            ':instruction': instruction,
            ':step_type': step_type
        }
        
        # Add optional fields if provided
        optional_fields = {
            'secret_key': body.get('secret_key'),
            'validation_type': body.get('validation_type'),
            'validation_operator': body.get('validation_operator'),
            'validation_value': body.get('validation_value'),
            'capture_variable': body.get('capture_variable'),
            'assertion_variable': body.get('assertion_variable'),
            'value_type': body.get('value_type'),
            'enable_advanced_click_types': body.get('enable_advanced_click_types'),
            'value_source': body.get('value_source'),
        }
        
        for field_name, field_value in optional_fields.items():
            if field_value:
                update_expression_parts.append(f'{field_name} = :{field_name}')
                expression_attribute_values[f':{field_name}'] = field_value
        
        update_expression = 'SET ' + ', '.join(update_expression_parts)
        
        # Update the step
        table.update_item(
            Key={
                'pk': f'USECASE#{usecase_id}',
                'sk': f'STEP#{step_id}'
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values
        )
        
        return create_response(200, {
            'status': 'step updated',
            'stepId': step_id
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error updating step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
