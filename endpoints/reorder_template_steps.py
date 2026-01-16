import logging
import json
from typing import Any, Dict, List
import boto3
from utils import create_response, get_table_name

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
        logger.info(f"Received request: {event}")
        
        # Get template ID from path
        path_params = event.get('pathParameters', {})
        template_id = path_params.get('id')
        
        if not template_id:
            return create_response(400, {'error': 'template ID is required'})
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid request body'})
        
        step_orders = body.get('step_orders', [])
        
        if not step_orders:
            return create_response(400, {'error': 'step_orders is required'})
        
        # Initialize DynamoDB client
        dynamodb_client = boto3.client('dynamodb')
        table_name = get_table_name()
        
        # Use a transaction to update all steps atomically
        transact_items = []
        
        for step_order in step_orders:
            step_id = step_order.get('step_id')
            sort_value = step_order.get('sort')
            
            transact_item = {
                'Update': {
                    'TableName': table_name,
                    'Key': {
                        'pk': {'S': f'TEMPLATE#{template_id}'},
                        'sk': {'S': f'STEP#{step_id}'}
                    },
                    'UpdateExpression': 'SET sort = :sort',
                    'ExpressionAttributeValues': {
                        ':sort': {'N': str(sort_value)}
                    }
                }
            }
            
            transact_items.append(transact_item)
        
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
