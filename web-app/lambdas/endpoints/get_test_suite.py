import logging
import boto3
from typing import Any, Dict
from utils import (
    create_response,
    get_table_name,
    require_scopes
)
from test_suite_schema import get_test_suites_pk, get_suite_sk

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get a specific test suite by ID.
    
    Validates user has read access to suite scope and returns the suite
    object with all metadata.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with test suite object
    """
    try:
        # Extract suite_id from path parameters
        path_params = event.get('pathParameters', {})
        suite_id = path_params.get('suite_id')
        
        if not suite_id:
            return create_response(400, {'error': 'suite_id is required'})
        
        # Validate scope access (requires api/suite.read or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.read'])
        if error_response:
            return error_response
        
        logger.info(f"Getting test suite {suite_id} for user: {user_identity.get('identity')}")
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get suite from Amazon DynamoDB
        response = table.get_item(
            Key={
                'pk': get_test_suites_pk(),
                'sk': get_suite_sk(suite_id)
            }
        )
        
        # Check if suite exists
        if 'Item' not in response:
            logger.warning(f"Test suite {suite_id} not found")
            return create_response(404, {'error': 'Test suite not found'})
        
        suite = response['Item']
        
        logger.info(f"Successfully retrieved test suite {suite_id}")
        
        # Return the suite (remove pk/sk from response)
        response_suite = {k: v for k, v in suite.items() if k not in ['pk', 'sk']}
        
        return create_response(200, response_suite)
        
    except Exception as e:
        logger.error(f"Error getting test suite: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
