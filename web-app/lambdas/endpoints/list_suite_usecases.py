import logging
import json
import boto3
from typing import Any, Dict, List
from utils import (
    create_response,
    get_table_name,
    require_scopes,
    validate_path_id)
from test_suite_schema import (
    get_suite_mapping_pk,
    get_test_suites_pk,
    get_suite_sk
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list use cases in a test suite.
    
    Validates user has read access to suite scope, queries all use case
    mappings for the suite, and returns array of use case objects with metadata.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with array of use case objects
    """
    try:
        # Get suite ID from path parameters
        suite_id, error = validate_path_id(event.get('pathParameters', {}).get('suite_id'), 'suite ID')
        if error:
            return error
        
        # Validate scope access (requires api/suite.read or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.read'])
        if error_response:
            return error_response
        
        user_identity_str = user_identity.get('identity', '')
        
        logger.info(f"Listing use cases for suite {suite_id} for user: {user_identity_str}")
        
        # Initialize Amazon DynamoDB client
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
        
        # Query all use case mappings for this suite
        mappings_response = table.query(
            KeyConditionExpression='pk = :pk AND begins_with(sk, :sk_prefix)',
            ExpressionAttributeValues={
                ':pk': get_suite_mapping_pk(suite_id),
                ':sk_prefix': 'USECASE#'
            }
        )
        
        mapping_items = mappings_response.get('Items', [])
        
        # Resolve current usecase names from canonical records via BatchGetItem
        canonical_lookup: Dict[str, Dict] = {}
        if mapping_items:
            usecase_ids = [item['usecase_id'] for item in mapping_items]
            table_name = get_table_name()
            
            # Process in batches of 25 (DynamoDB BatchGetItem limit)
            for i in range(0, len(usecase_ids), 25):
                batch_ids = usecase_ids[i:i + 25]
                keys = [
                    {'pk': 'USECASES', 'sk': f'USECASE#{uid}'}
                    for uid in batch_ids
                ]
                
                request_items = {table_name: {'Keys': keys}}
                while request_items:
                    batch_response = dynamodb.batch_get_item(RequestItems=request_items)
                    
                    for record in batch_response.get('Responses', {}).get(table_name, []):
                        canonical_lookup[record['id']] = record
                    
                    # Handle UnprocessedKeys with retry
                    request_items = batch_response.get('UnprocessedKeys', {})
        
        usecases = []
        for item in mapping_items:
            usecase_id = item.get('usecase_id')
            canonical = canonical_lookup.get(usecase_id)
            usecase_obj = {
                'usecase_id': usecase_id,
                'usecase_name': canonical['name'] if canonical else item.get('usecase_name', ''),
                'added_by': item.get('added_by'),
                'added_at': item.get('added_at')
            }
            usecases.append(usecase_obj)
        
        logger.info(f"Found {len(usecases)} use cases in suite {suite_id}")
        
        return create_response(200, {
            'usecases': usecases,
            'total': len(usecases)
        })
        
    except Exception as e:
        logger.error(f"Error listing suite use cases: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
