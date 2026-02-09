import logging
import json
import os
from typing import Any, Dict
from uuid import uuid4
import boto3
from utils import create_response, get_table_name, get_current_timestamp, require_user_token

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a new usecase.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created usecase
    """
    try:
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Validate user token (M2M tokens not allowed for creating use cases)
        user_identity, error_response = require_user_token(event)
        if error_response:
            return error_response
        
        user_email = user_identity.get('email', '')
        user_sub = user_identity.get('sub', '')
        
        logger.info(f"Creating usecase for user: {user_email}")
        
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Generate usecase ID
        usecase_id = str(uuid4())
        now = get_current_timestamp()
        
        # Set default model if not provided
        model_id = body.get('model_id', 'nova-act-v1.0')
        
        # Set default region if not provided (use environment variable or fallback)
        default_region = os.environ.get('DEFAULT_REGION', 'us-east-1')
        executing_region = body.get('executing_region', default_region) or default_region  # Handle empty string too
        
        # Create usecase
        usecase = {
            'pk': 'USECASES',
            'sk': f'USECASE#{usecase_id}',
            'id': usecase_id,
            'name': body.get('name', ''),
            'description': body.get('description', ''),
            'starting_url': body.get('starting_url', ''),
            'active': body.get('active', False),
            'tags': body.get('tags', []),
            'created_at': now,
            'executing_region': executing_region,
            'model_id': model_id
        }
        
        # Create created_by record
        created_by_record = {
            'pk': f'USECASE#{usecase_id}',
            'sk': 'CREATED_BY',
            'email': user_email,
            'sub': user_sub,
            'created_at': now
        }
        
        # Use transact_write_items to ensure both records are created atomically
        dynamodb_client = boto3.client('dynamodb')
        
        # Convert usecase to DynamoDB format
        usecase_item = {}
        for key, value in usecase.items():
            if isinstance(value, str):
                usecase_item[key] = {'S': value}
            elif isinstance(value, bool):
                usecase_item[key] = {'BOOL': value}
            elif isinstance(value, list):
                if value:  # Only add if list is not empty
                    usecase_item[key] = {'L': [{'S': item} for item in value]}
                else:
                    usecase_item[key] = {'L': []}
        
        # Convert created_by to DynamoDB format
        created_by_item = {
            'pk': {'S': created_by_record['pk']},
            'sk': {'S': created_by_record['sk']},
            'email': {'S': created_by_record['email']},
            'sub': {'S': created_by_record['sub']},
            'created_at': {'S': created_by_record['created_at']}
        }
        
        dynamodb_client.transact_write_items(
            TransactItems=[
                {
                    'Put': {
                        'TableName': get_table_name(),
                        'Item': usecase_item
                    }
                },
                {
                    'Put': {
                        'TableName': get_table_name(),
                        'Item': created_by_item
                    }
                }
            ]
        )
        
        logger.info(f"Successfully created usecase {usecase_id}")
        
        return create_response(201, usecase)
        
    except Exception as e:
        logger.error(f"Error creating usecase: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
