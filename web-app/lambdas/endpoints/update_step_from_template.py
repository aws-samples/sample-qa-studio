import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, validate_path_id
from resource_auth import require_resource_access, usecase_from_path
from step_copy import copy_step_fields
from template_store import get_template_metadata

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write', 'api/templates.read'])
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
        # Get parameters from path
        usecase_id = event['pathParameters']['id']  # validated by the resolver

        step_id, error = validate_path_id(event.get('pathParameters', {}).get('stepId'), 'step ID')
        if error:
            return error
        
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
        template = get_template_metadata(table, template_id)
        if template is None:
            return create_response(404, {'error': 'Template not found'})
        
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
            # Update template reference
            'template_id': template_id,
            'template_step_id': template_step_id,
            'template_version': template.get('version', 1),
            # Update from template (instruction, step_type and every authored field)
            **copy_step_fields(template_step),
        }
        
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
