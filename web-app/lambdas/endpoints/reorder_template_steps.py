import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, require_scopes, validate_path_id, request_log_summary
from template_store import bump_template_version_transact_item
from step_reorder import parse_step_orders, sort_update_items

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to reorder template steps.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with reorder confirmation
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/templates.write'])
        if error:
            return error
        
        logger.info(f"Received request: {request_log_summary(event)}")
        
        # Get template ID from path
        template_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        step_orders, error = parse_step_orders(event)
        if error:
            return error

        dynamodb_client = boto3.client('dynamodb')
        table_name = get_table_name()

        transact_items = sort_update_items(
            table_name, f'TEMPLATE#{template_id}', step_orders, sk_for=lambda step_id: f'STEP#{step_id}',
        )

        # One version bump per reorder, atomic with the step updates
        transact_items.append(bump_template_version_transact_item(table_name, template_id))
        
        # Execute the transaction
        dynamodb_client.transact_write_items(TransactItems=transact_items)
        
        logger.info(f"Successfully reordered {len(step_orders)} template steps for template {template_id}")
        
        return create_response(200, {
            'message': 'Template steps reordered successfully',
            'count': len(step_orders)
        })
        
    except Exception as e:
        logger.error(f"Error reordering template steps: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Failed to update template step orders'})
