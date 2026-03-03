"""
List Suite Executions Lambda Function

This function lists all executions for a test suite with:
1. Validation that user has read access to suite scope
2. Query pk = 'SUITE_EXECUTION#{suite_id}', sk begins_with 'EXECUTION#'
3. Support for pagination (limit parameter)
4. Support for status filtering
5. Return array of execution objects sorted by started_at descending
"""

import logging
import json
import boto3
from typing import Any, Dict, List
from boto3.dynamodb.conditions import Key
from utils import (
    create_response,
    get_table_name,
    require_scopes
)
from test_suite_schema import (
    get_test_suites_pk,
    get_suite_sk,
    get_suite_execution_pk
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list executions for a test suite.
    
    Validates user has read access to suite scope, queries all executions
    for the suite, supports pagination and status filtering, and returns
    array of execution objects sorted by started_at descending.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with array of execution objects
    """
    try:
        # Get suite ID from path parameters
        suite_id = event.get('pathParameters', {}).get('suite_id')
        if not suite_id:
            return create_response(400, {'error': 'Missing suite ID'})
        
        # Validate scope access (requires api/suite.read or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.read'])
        if error_response:
            return error_response
        
        user_identity_str = user_identity.get('identity', '')
        
        # Get query parameters
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 10))
        status_filter = query_params.get('status')
        
        # Validate limit parameter
        if limit < 1 or limit > 100:
            return create_response(400, {'error': 'Limit must be between 1 and 100'})
        
        # Validate status filter if provided
        valid_statuses = ['pending', 'running', 'completed', 'partial', 'failed']
        if status_filter and status_filter not in valid_statuses:
            return create_response(400, {
                'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            })
        
        logger.info(f"Listing executions for suite {suite_id} for user: {user_identity_str}, limit: {limit}, status: {status_filter}")
        
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
        
        # Query all executions for this suite
        executions_response = table.query(
            KeyConditionExpression=Key('pk').eq(get_suite_execution_pk(suite_id)) & Key('sk').begins_with('EXECUTION#'),
            ScanIndexForward=False  # Sort by sk descending (most recent first)
        )
        
        executions = executions_response.get('Items', [])
        
        # Apply status filter if specified
        if status_filter:
            executions = [
                exec_item for exec_item in executions
                if exec_item.get('status') == status_filter
            ]
            logger.info(f"After status filter '{status_filter}': {len(executions)} executions")
        
        # Sort by started_at descending (most recent first)
        # Note: UUIDv7 in sk already provides time-ordering, but we sort by started_at for clarity
        executions.sort(key=lambda x: x.get('started_at', ''), reverse=True)
        
        # Apply pagination limit
        paginated_executions = executions[:limit]
        
        # Remove pk/sk from response objects
        response_executions = [
            {k: v for k, v in exec_item.items() if k not in ['pk', 'sk']}
            for exec_item in paginated_executions
        ]
        
        logger.info(f"Returning {len(response_executions)} executions for suite {suite_id}")
        
        return create_response(200, {
            'executions': response_executions,
            'total': len(response_executions),
            'has_more': len(executions) > limit
        })
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return create_response(400, {'error': str(e)})
    except Exception as e:
        logger.error(f"Error listing suite executions: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
