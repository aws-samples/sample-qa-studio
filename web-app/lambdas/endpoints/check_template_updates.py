import logging
import json
from typing import Any, Dict, List
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to check for template updates for usecase steps.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with update information
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/templates.read'])
        if error:
            return error
        
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id = path_params.get('id')
        
        if not usecase_id:
            return create_response(400, {'error': 'Missing usecase ID'})
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get all steps for this usecase
        steps_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('STEP#')
        )
        
        steps = steps_response.get('Items', [])
        updates: List[Dict[str, Any]] = []
        
        # Check each step that has a template reference
        for step in steps:
            template_id = step.get('template_id')
            if not template_id:
                continue
            
            # Get the template metadata to check current version
            try:
                template_response = table.get_item(
                    Key={
                        'pk': f'TEMPLATE#{template_id}',
                        'sk': 'METADATA'
                    }
                )
                
                if 'Item' not in template_response:
                    logger.warning(f"Template {template_id} not found")
                    continue
                
                template = template_response['Item']
                current_version = step.get('template_version', 0)
                latest_version = template.get('version', 0)
                
                # Check if there's an update available
                has_update = latest_version > current_version
                
                updates.append({
                    'step_id': step.get('id'),
                    'current_version': current_version,
                    'latest_version': latest_version,
                    'has_update': has_update,
                    'template_id': template_id,
                    'template_step_id': step.get('template_step_id', '')
                })
                
            except Exception as e:
                logger.error(f"Error checking template {template_id}: {str(e)}")
                continue
        
        return create_response(200, {'updates': updates})
        
    except Exception as e:
        logger.error(f"Error checking template updates: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
