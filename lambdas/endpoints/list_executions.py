import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import get_table_name, create_response, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list executions for a specific use case from DynamoDB.
    Accessible by both user tokens and M2M tokens.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of executions
    """
    try:
        # Validate scope (requires executions.read or admin)
        user_identity, error_response = require_scopes(event, ['api/executions.read'])
        if error_response:
            return error_response
        
        # Get use case ID from path parameters
        usecase_id = event.get('pathParameters', {}).get('id')
        if not usecase_id:
            return create_response(400, {'error': 'Missing use case ID'})
        
        # Get limit from query string parameters (default to 20)
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 20))
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Query DynamoDB for all executions of this use case
        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE_EXECUTION#{usecase_id}') & Key('sk').begins_with('EXECUTION#'),
            Limit=limit,
            ScanIndexForward=False  # Sort descending (newest first)
        )
        
        executions = response.get('Items', [])
        
        # Sort by created_at descending (newest first) - additional sort for consistency
        executions.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Return successful response
        return create_response(200, {'executions': executions})
        
    except ValueError as e:
        logger.error(f"Invalid limit parameter: {str(e)}")
        return create_response(400, {'error': 'Invalid limit parameter'})
    except Exception as e:
        logger.error(f"Error listing executions: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
