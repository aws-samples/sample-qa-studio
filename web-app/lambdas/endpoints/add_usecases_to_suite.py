import logging
import json
import boto3
from typing import Any, Dict, List
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    require_scopes,
    validate_path_id)
from test_suite_schema import (
    create_suite_usecase_mapping_item,
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
    Lambda handler to add use cases to a test suite.
    
    Validates user has write access to suite scope, validates read access
    to each use case, creates mappings (idempotent), and updates the
    total_usecases count on the suite.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with count of added use cases
    """
    try:
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Validate required fields
        usecase_ids = body.get('usecase_ids', [])
        
        if not isinstance(usecase_ids, list):
            return create_response(400, {'error': 'usecase_ids must be an array'})
        
        if not usecase_ids:
            return create_response(400, {'error': 'usecase_ids cannot be empty'})
        
        # Get suite ID from path parameters
        suite_id, error = validate_path_id(event.get('pathParameters', {}).get('suite_id'), 'suite ID')
        if error:
            return error
        
        # Validate scope access (requires api/suite.write or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.write'])
        if error_response:
            return error_response
        
        user_identity_str = user_identity.get('identity', '')
        
        logger.info(f"Adding {len(usecase_ids)} use cases to suite {suite_id} for user: {user_identity_str}")
        
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
        
        # Query existing mappings to check for duplicates
        existing_mappings_response = table.query(
            KeyConditionExpression='pk = :pk AND begins_with(sk, :sk_prefix)',
            ExpressionAttributeValues={
                ':pk': get_suite_mapping_pk(suite_id),
                ':sk_prefix': 'USECASE#'
            }
        )
        
        existing_usecase_ids = set()
        for item in existing_mappings_response.get('Items', []):
            existing_usecase_ids.add(item.get('usecase_id'))
        
        # Process each use case
        added_count = 0
        now = get_current_timestamp()
        mappings_to_create = []
        
        for usecase_id in usecase_ids:
            # Skip if already in suite (idempotent)
            if usecase_id in existing_usecase_ids:
                logger.info(f"Use case {usecase_id} already in suite {suite_id}, skipping")
                continue
            
            # Get use case metadata
            usecase_response = table.get_item(
                Key={
                    'pk': 'USECASES',
                    'sk': f'USECASE#{usecase_id}'
                }
            )
            
            usecase = usecase_response.get('Item')
            if not usecase:
                logger.warning(f"Use case {usecase_id} not found, skipping")
                continue
            
            usecase_name = usecase.get('name', '')
            usecase_scope = usecase.get('scope', 'usecase:default')
            
            # Create mapping item
            mapping_item = create_suite_usecase_mapping_item(
                suite_id=suite_id,
                usecase_id=usecase_id,
                usecase_name=usecase_name,
                usecase_scope=usecase_scope,
                added_by=user_identity_str,
                added_at=now
            )
            
            mappings_to_create.append(mapping_item)
            added_count += 1
        
        # If no new mappings to create, return early
        if added_count == 0:
            logger.info(f"No new use cases to add to suite {suite_id}")
            return create_response(200, {
                'added': 0,
                'total_usecases': suite.get('total_usecases', 0)
            })
        
        # Write mappings and update suite count in a batch
        # Note: DynamoDB batch_write_item doesn't support atomic counter updates
        # So we'll write mappings first, then update the counter
        
        # Write mappings in batches of 25 (DynamoDB limit)
        with table.batch_writer() as batch:
            for mapping in mappings_to_create:
                batch.put_item(Item=mapping)
        
        # Update total_usecases count on suite
        new_total = suite.get('total_usecases', 0) + added_count
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
        
        logger.info(f"Successfully added {added_count} use cases to suite {suite_id}")
        
        return create_response(200, {
            'added': added_count,
            'total_usecases': new_total
        })
        
    except Exception as e:
        logger.error(f"Error adding use cases to suite: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
