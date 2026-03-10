import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update a step from its template.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with update confirmation
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/usecases.write'])
        if error:
            return error
        
        # Get parameters from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        step_id = path_params.get('stepId')
        
        if not usecase_id or not step_id:
            return create_response(400, {'error': 'Missing usecase ID or step ID'})
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # 1. Get the current step
        step_response = table.get_item(
            Key={
                'pk': f'USECASE#{usecase_id}',
                'sk': f'STEP#{step_id}'
            }
        )
        
        if 'Item' not in step_response:
            return create_response(404, {'error': 'Step not found'})
        
        current_step = step_response['Item']
        
        if not current_step.get('template_id'):
            return create_response(400, {'error': 'Step is not from a template'})
        
        template_id = current_step['template_id']
        template_step_id = current_step.get('template_step_id')
        
        # 2. Get the template metadata
        template_response = table.get_item(
            Key={
                'pk': 'TEMPLATES',
                'sk': f'TEMPLATE#{template_id}'
            }
        )
        
        if 'Item' not in template_response:
            return create_response(404, {'error': 'Template not found'})
        
        template = template_response['Item']
        
        # 3. Get the template step
        template_step_response = table.get_item(
            Key={
                'pk': f'TEMPLATE#{template_id}',
                'sk': f'STEP#{template_step_id}'
            }
        )
        
        if 'Item' not in template_step_response:
            return create_response(404, {'error': 'Template step not found'})
        
        template_step = template_step_response['Item']
        
        # 4. Update the step with template data (keep PK, SK, ID, Sort, CreatedAt)
        updated_step = {
            'pk': current_step['pk'],
            'sk': current_step['sk'],
            'id': current_step['id'],
            'sort': current_step['sort'],
            'created_at': current_step['created_at'],
            # Update from template
            'instruction': template_step.get('instruction', ''),
            'step_type': template_step.get('step_type', ''),
            # Update template reference
            'template_id': template_id,
            'template_step_id': template_step_id,
            'template_version': template.get('version', 1)
        }
        
        # Add optional fields from template if present
        if template_step.get('secret_key'):
            updated_step['secret_key'] = template_step['secret_key']
        if template_step.get('capture_variable'):
            updated_step['capture_variable'] = template_step['capture_variable']
        if template_step.get('validation_type'):
            updated_step['validation_type'] = template_step['validation_type']
        if template_step.get('validation_operator'):
            updated_step['validation_operator'] = template_step['validation_operator']
        if template_step.get('validation_value'):
            updated_step['validation_value'] = template_step['validation_value']
        if template_step.get('assertion_variable'):
            updated_step['assertion_variable'] = template_step['assertion_variable']
        if template_step.get('value_type'):
            updated_step['value_type'] = template_step['value_type']
        
        # Save updated step
        table.put_item(Item=updated_step)
        
        logger.info(f"Updated step {step_id} from template {template_id} (v{current_step.get('template_version', 0)} -> v{template.get('version', 1)})")
        
        return create_response(200, {
            'message': 'Step updated from template',
            'previous_version': current_step.get('template_version', 0),
            'new_version': template.get('version', 1)
        })
        
    except Exception as e:
        logger.error(f"Error updating step from template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
