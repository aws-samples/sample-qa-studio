import logging
import boto3
from typing import Any, Dict
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    require_scopes
)
from test_suite_schema import (
    get_suite_mapping_pk,
    get_usecase_mapping_sk,
    get_test_suites_pk,
    get_suite_sk
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to remove a use case from a test suite.
    
    Validates user has write access to suite scope, deletes the mapping item
    from DynamoDB, decrements the total_usecases count on the suite, and
    returns 204 No Content.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with 204 No Content
    """
    try:
        # Get suite ID and usecase ID from path parameters
        path_params = event.get('pathParameters', {})
        suite_id = path_params.get('suite_id')
        usecase_id = path_params.get('usecase_id')
        
        if not suite_id:
            return create_response(400, {'error': 'Missing suite ID'})
        
        if not usecase_id:
            return create_response(400, {'error': 'Missing usecase ID'})
        
        # Validate scope access (requires api/suite.write or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.write'])
        if error_response:
            return error_response
        
        user_identity_str = user_identity.get('identity', '')
        
        logger.info(f"Removing use case {usecase_id} from suite {suite_id} for user: {user_identity_str}")
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get the test suite to validate it exists
        suite_response = table.get_item(
            Key={
                'pk': get_test_suites_pk(),
                'sk': get_suite_sk(suite_id)
            }
        )
        
        suite = suite_response.get('Item')
        if not suite:
            return create_response(404, {'error': 'Test suite not found'})
        
        # Check if mapping exists
        mapping_response = table.get_item(
            Key={
                'pk': get_suite_mapping_pk(suite_id),
                'sk': get_usecase_mapping_sk(usecase_id)
            }
        )
        
        mapping = mapping_response.get('Item')
        if not mapping:
            logger.info(f"Mapping for use case {usecase_id} in suite {suite_id} not found")
            return create_response(404, {'error': 'Use case not found in suite'})
        
        # Delete mapping item from DynamoDB
        table.delete_item(
            Key={
                'pk': get_suite_mapping_pk(suite_id),
                'sk': get_usecase_mapping_sk(usecase_id)
            }
        )
        
        logger.info(f"Deleted mapping: {get_suite_mapping_pk(suite_id)} / {get_usecase_mapping_sk(usecase_id)}")
        
        # Decrement total_usecases count on suite
        current_total = suite.get('total_usecases', 0)
        new_total = max(0, current_total - 1)  # Ensure we don't go negative
        now = get_current_timestamp()
        
        table.update_item(
            Key={
                'pk': get_test_suites_pk(),
                'sk': get_suite_sk(suite_id)
            },
            UpdateExpression='SET total_usecases = :total, updated_at = :updated_at',
            ExpressionAttributeValues={
                ':total': new_total,
                ':updated_at': now
            }
        )
        
        logger.info(f"Successfully removed use case {usecase_id} from suite {suite_id}")
        
        # Return 204 No Content
        return {
            'statusCode': 204,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': ''
        }
        
    except Exception as e:
        logger.error(f"Error removing use case from suite: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
