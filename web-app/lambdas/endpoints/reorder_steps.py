import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, request_log_summary
from resource_auth import require_resource_access, usecase_from_path
from step_reorder import parse_step_orders, sort_update_items

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to reorder usecase steps.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with reorder confirmation
    """
    try:
        logger.info(f"Received request: {request_log_summary(event)}")
        
        # Get usecase ID from path
        usecase_id = event['pathParameters']['id']  # validated by the resolver
        
        step_orders, error = parse_step_orders(event)
        if error:
            return error

        dynamodb_client = boto3.client('dynamodb')
        table_name = get_table_name()

        # The UI sends the full STEP#... sort key as step_id.
        transact_items = sort_update_items(
            table_name, f'USECASE#{usecase_id}', step_orders, sk_for=lambda step_id: step_id,
        )

        # Execute the transaction
        dynamodb_client.transact_write_items(TransactItems=transact_items)
        
        logger.info(f"Successfully reordered {len(step_orders)} steps for usecase {usecase_id}")
        
        return create_response(200, {
            'message': 'Steps reordered successfully',
            'count': len(step_orders)
        })
        
    except Exception as e:
        logger.error(f"Error reordering steps: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Failed to update step orders'})
