import logging
from typing import Any, Dict
import boto3
from utils import no_content_response, get_table_name, create_response, validate_path_id
from resource_auth import require_resource_access, usecase_from_path
from repeat_validation import REPEAT_STEP_TYPE, children_of, load_usecase_steps
from template_usage import remove_usage_if_unlinked

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a step from Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Get usecase ID and step ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by the resolver

        step_id, error = validate_path_id(event.get('pathParameters', {}).get('stepId'), 'step ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        # A repeat step takes its children with it (server-side cascade).
        deleted_step_ids = [step_id]
        siblings = load_usecase_steps(table, usecase_id)
        target = next((s for s in siblings if s.get('id') == step_id), None)
        if target is not None and target.get('step_type') == REPEAT_STEP_TYPE:
            deleted_step_ids.extend(child['id'] for child in children_of(siblings, step_id) if child.get('id'))

        # Delete the step (and any children)
        for deleted_id in deleted_step_ids:
            table.delete_item(
                Key={
                    'pk': f'USECASE#{usecase_id}',
                    'sk': f'STEP#{deleted_id}'
                }
            )

        # Was this the last step linked to its template? Then the template's
        # USAGE record for this use case is stale.
        if target is not None and target.get('template_id'):
            remove_usage_if_unlinked(table, target['template_id'], usecase_id)
        
        return no_content_response()
        
    except Exception as e:
        logger.error(f"Error deleting step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
