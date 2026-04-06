import logging
import json
import os
from typing import Any, Dict
from uuid import uuid4
import boto3
from utils import create_response, get_table_name, get_current_timestamp, require_scopes

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
        
        # Validate scope (requires usecases.write or admin)
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        user_email = user_identity.get('email', '')
        user_sub = user_identity.get('sub', '')
        
        logger.info(f"Creating usecase for user: {user_email}")
        
        # Initialize Amazon DynamoDB client
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
        
        # Extract mobile fields
        test_platform = body.get('test_platform', '') or 'web'  # Default to "web" when absent or empty
        platform = body.get('platform', '')
        app_package = body.get('app_package', '')
        app_activity = body.get('app_activity', '')
        bundle_id = body.get('bundle_id', '')
        device_farm_project_arn = body.get('device_farm_project_arn', '')
        device_arn = body.get('device_arn', '')
        
        # Mobile-specific validation
        if test_platform == 'mobile':
            if platform not in ('ANDROID', 'IOS'):
                return create_response(400, {'error': 'platform must be "ANDROID" or "IOS" when test_platform is "mobile"'})
            
            if platform == 'ANDROID':
                if not app_package:
                    return create_response(400, {'error': 'app_package is required when platform is "ANDROID"'})
                if not app_activity:
                    return create_response(400, {'error': 'app_activity is required when platform is "ANDROID"'})
            
            if platform == 'IOS':
                if not bundle_id:
                    return create_response(400, {'error': 'bundle_id is required when platform is "IOS"'})

            # Validate device_arn format if provided
            if device_arn and not device_arn.startswith('arn:aws:devicefarm:'):
                return create_response(400, {'error': 'Invalid device_arn format — must be a Device Farm device ARN'})
        
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
            'model_id': model_id,
            'enable_cache': body.get('enableCache', False),
            'test_platform': test_platform,
        }
        
        # Store mobile config fields only when non-empty
        mobile_fields = {
            'platform': platform,
            'app_package': app_package,
            'app_activity': app_activity,
            'bundle_id': bundle_id,
            'device_farm_project_arn': device_farm_project_arn,
            'device_arn': device_arn,
        }
        for field_name, field_value in mobile_fields.items():
            if field_value:
                usecase[field_name] = field_value
        
        # Create created_by record
        created_by_record = {
            'pk': f'USECASE#{usecase_id}',
            'sk': 'CREATED_BY',
            'email': user_email,
            'sub': user_sub,
            'created_at': now
        }
        
        # Use transact_write_items so both records are created atomically
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
