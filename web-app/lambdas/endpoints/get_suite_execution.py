"""
Get Suite Execution Lambda Function

This function retrieves a specific suite execution with all its results:
1. Validates user has read access to suite scope
2. Gets suite execution metadata
3. Queries all execution results (pk = 'SUITE_EXEC#{execution_id}')
4. Returns execution object with results array
"""

import logging
import boto3
from typing import Any, Dict
from boto3.dynamodb.conditions import Key
from utils import (
    create_response,
    get_table_name,
    require_scopes
)
from test_suite_schema import (
    get_suite_execution_pk,
    get_execution_sk,
    get_suite_exec_result_pk
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to get a specific suite execution with all results.
    
    Validates user has read access to suite scope, retrieves execution
    metadata, queries all execution results, and returns complete execution
    object with embedded results array.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with execution object and results
    """
    try:
        # Get suite_id and execution_id from path parameters
        path_params = event.get('pathParameters', {})
        suite_id = path_params.get('suite_id')
        execution_id = path_params.get('execution_id')
        
        if not suite_id:
            return create_response(400, {'error': 'Missing suite ID'})
        
        if not execution_id:
            return create_response(400, {'error': 'Missing execution ID'})
        
        # Validate scope access (requires api/suite.read or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.read'])
        if error_response:
            return error_response
        
        user_identity_str = user_identity.get('identity', '')
        
        logger.info(f"Getting suite execution {execution_id} for suite {suite_id} for user: {user_identity_str}")
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get suite execution metadata
        execution_response = table.get_item(
            Key={
                'pk': get_suite_execution_pk(suite_id),
                'sk': get_execution_sk(execution_id)
            }
        )
        
        execution = execution_response.get('Item')
        if not execution:
            logger.warning(f"Suite execution {execution_id} not found")
            return create_response(404, {'error': 'Suite execution not found'})
        
        # Query actual use case executions that are part of this suite execution
        # Use GSI to efficiently query by suite_execution_id
        results = []
        query_kwargs = {
            'IndexName': 'suite-execution-index',
            'KeyConditionExpression': Key('suite_execution_id').eq(execution_id)
        }
        
        # Paginate through all results
        while True:
            query_response = table.query(**query_kwargs)
            results.extend(query_response.get('Items', []))
            
            # Check if there are more pages
            if 'LastEvaluatedKey' not in query_response:
                break
            query_kwargs['ExclusiveStartKey'] = query_response['LastEvaluatedKey']
        
        logger.info(f"Found {len(results)} use case executions for suite execution {execution_id}")
        
        # Remove pk/sk from execution object
        response_execution = {k: v for k, v in execution.items() if k not in ['pk', 'sk']}
        
        # Transform results to include usecase_id, execution_id, and usecase_name
        response_results = []
        for result in results:
            # Extract usecase_id and execution_id from pk/sk
            pk = result.get('pk', '')
            sk = result.get('sk', '')
            
            # pk format: USECASE_EXECUTION#{usecase_id}
            # sk format: EXECUTION#{execution_id}
            usecase_id = pk.replace('USECASE_EXECUTION#', '') if pk.startswith('USECASE_EXECUTION#') else ''
            usecase_execution_id = sk.replace('EXECUTION#', '') if sk.startswith('EXECUTION#') else ''
            
            # Use denormalized usecase_name from execution record (stored during creation)
            # Fall back to lookup only if not present (legacy records)
            usecase_name = result.get('usecase_name', '')
            if not usecase_name and usecase_id:
                try:
                    usecase_response = table.get_item(
                        Key={
                            'pk': 'USECASES',
                            'sk': f'USECASE#{usecase_id}'
                        }
                    )
                    if 'Item' in usecase_response:
                        usecase_name = usecase_response['Item'].get('name', '')
                except Exception as e:
                    logger.warning(f"Failed to fetch use case name for {usecase_id}: {e}")
            
            result_item = {k: v for k, v in result.items() if k not in ['pk', 'sk']}
            result_item['usecase_id'] = usecase_id
            result_item['usecase_execution_id'] = usecase_execution_id
            result_item['usecase_name'] = usecase_name
            response_results.append(result_item)
        
        # Embed results array in execution object
        response_execution['results'] = response_results
        
        logger.info(f"Successfully retrieved suite execution {execution_id} with {len(response_results)} results")
        
        return create_response(200, response_execution)
        
    except Exception as e:
        logger.error(f"Error getting suite execution: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
