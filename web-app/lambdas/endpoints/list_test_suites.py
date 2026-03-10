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
from test_suite_schema import get_test_suites_pk

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list all test suites.
    
    Queries all test suites from DynamoDB and supports optional tag and scope query parameters.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with list of test suites
    """
    try:
        # Validate scope (requires api/suite.read or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.read'])
        if error_response:
            return error_response
        
        logger.info(f"Listing test suites for user: {user_identity.get('identity')}")
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Query all test suites
        response = table.query(
            KeyConditionExpression=Key('pk').eq(get_test_suites_pk())
        )
        
        suites = response.get('Items', [])
        logger.info(f"Retrieved {len(suites)} test suites from DynamoDB")
        
        # Remove pk/sk and unnecessary fields from response objects
        response_suites = []
        for suite in suites:
            suite_data = {k: v for k, v in suite.items() if k not in [
                'pk', 'sk', 'scope', 'schedule_expression', 'schedule_enabled',
                'last_successful_count'
            ]}
            response_suites.append(suite_data)
        
        return create_response(200, {'suites': response_suites})
        
    except Exception as e:
        logger.error(f"Error listing test suites: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
