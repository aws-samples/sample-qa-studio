import logging
import os
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from utils import (
    create_response,
    get_table_name,
    require_scopes,
    validate_path_id)
from test_suite_schema import (
    get_test_suites_pk,
    get_suite_sk,
    get_suite_mapping_pk
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to delete a test suite and all related data.
    
    Validates user has write access to suite scope, deletes suite item from
    DynamoDB, queries and deletes all suite-usecase mappings, disables
    Amazon EventBridge schedule if exists, and returns 204 No Content.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with 204 No Content
    """
    try:
        # Extract suite_id from path parameters
        path_params = event.get('pathParameters', {})
        suite_id, error = validate_path_id(event.get('pathParameters', {}).get('suite_id'), 'suite ID')
        if error:
            return error
        
        # Validate scope access (requires api/suite.write or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.write'])
        if error_response:
            return error_response
        
        logger.info(f"Deleting test suite {suite_id} for user: {user_identity.get('identity')}")
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get existing suite to check schedule
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
        
        # Disable Amazon EventBridge schedule if exists
        if suite.get('schedule_enabled'):
            disable_suite_schedule(suite_id)
        
        # Query and delete all suite-usecase mappings
        mappings_response = table.query(
            KeyConditionExpression=Key('pk').eq(get_suite_mapping_pk(suite_id))
        )
        
        for mapping in mappings_response.get('Items', []):
            table.delete_item(
                Key={
                    'pk': mapping['pk'],
                    'sk': mapping['sk']
                }
            )
            logger.info(f"Deleted mapping: {mapping['pk']} / {mapping['sk']}")
        
        # Delete suite item from DynamoDB
        table.delete_item(
            Key={
                'pk': get_test_suites_pk(),
                'sk': get_suite_sk(suite_id)
            }
        )
        
        logger.info(f"Successfully deleted test suite {suite_id}")
        
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
        logger.error(f"Error deleting test suite: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


def disable_suite_schedule(suite_id: str) -> None:
    """
    Disable Amazon EventBridge schedule for the test suite.
    
    Args:
        suite_id: Test suite ID (used as schedule name)
    """
    try:
        # Get scheduler group name from environment
        scheduler_group_name = os.environ.get('SCHEDULER_GROUP_NAME')
        if not scheduler_group_name:
            logger.warning("SCHEDULER_GROUP_NAME environment variable not set, skipping schedule deletion")
            return
        
        # Initialize Amazon EventBridge Scheduler client
        scheduler_client = boto3.client('scheduler')
        
        # Delete the schedule
        scheduler_client.delete_schedule(
            Name=suite_id,
            GroupName=scheduler_group_name
        )
        
        logger.info(f"Successfully deleted schedule for suite {suite_id}")
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'ResourceNotFoundException':
            logger.info(f"Schedule for suite {suite_id} does not exist, nothing to delete")
        else:
            logger.warning(f"Could not delete schedule for suite {suite_id}: {str(e)}")
    except Exception as e:
        logger.warning(f"Warning: Could not delete schedule: {str(e)}")
