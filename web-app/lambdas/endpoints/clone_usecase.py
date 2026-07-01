import logging
import json
from typing import Any, Dict
from uuid import uuid4
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, get_secret_prefix, get_current_timestamp, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to clone a usecase with all its configuration.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with clone result
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/usecases.write'])
        if error:
            return error
        
        # Get source usecase ID from path
        source_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        name = body.get('name', '')
        if not name:
            return create_response(400, {
                'success': False,
                'message': 'Name is required'
            })
        
        # Extract user info for created_by tracking
        user_email = user_identity.get('email') or user_identity.get('identity', 'unknown')
        user_sub = user_identity.get('sub', '')
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        secrets_client = boto3.client('secretsmanager')
        
        # Get source usecase
        source_response = table.get_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{source_id}'
            }
        )
        
        if 'Item' not in source_response:
            return create_response(404, {
                'success': False,
                'message': 'Source usecase not found'
            })
        
        source_usecase = source_response['Item']
        
        # Generate new usecase ID
        new_usecase_id = str(uuid4())
        now = get_current_timestamp()
        
        # Create new usecase
        new_usecase = {
            'pk': 'USECASES',
            'sk': f'USECASE#{new_usecase_id}',
            'id': new_usecase_id,
            'name': name,
            'description': source_usecase.get('description', ''),
            'starting_url': source_usecase.get('starting_url', ''),
            'active': source_usecase.get('active', False),
            'region': source_usecase.get('region', ''),
            'executing_region': source_usecase.get('executing_region', ''),
            'tags': source_usecase.get('tags', []),
            'created_at': now,
            'test_platform': source_usecase.get('test_platform', 'web'),
        }

        # Copy mobile-specific fields if present
        for field in ['platform', 'app_package', 'app_activity', 'bundle_id',
                       'device_arn', 'model_id', 'enable_cache',
                       'app_binary_s3_path', 'app_arn', 'device_farm_project_arn',
                       'browser_policy_s3_path']:
            val = source_usecase.get(field)
            if val:
                new_usecase[field] = val
        
        # Save new usecase
        table.put_item(Item=new_usecase)
        
        # Save created_by record
        created_by_record = {
            'pk': f'USECASE#{new_usecase_id}',
            'sk': 'CREATED_BY',
            'email': user_email,
            'sub': user_sub,
            'created_at': now
        }
        table.put_item(Item=created_by_record)
        
        # Clone steps
        steps_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{source_id}') & Key('sk').begins_with('STEP#')
        )
        
        steps = steps_response.get('Items', [])
        steps.sort(key=lambda x: x.get('sort', 0))
        
        for step in steps:
            new_step_id = str(uuid4())
            new_step = {
                'pk': f'USECASE#{new_usecase_id}',
                'sk': f'STEP#{new_step_id}',
                'sort': step.get('sort', 0),
                'id': new_step_id,
                'instruction': step.get('instruction', ''),
                'step_type': step.get('step_type', ''),
                'created_at': now
            }
            
            # Copy optional fields
            for field in ['secret_key', 'capture_variable', 'validation_type', 
                         'validation_operator', 'validation_value', 'assertion_variable',
                         'value_step', 'value_type',
                         'network_url_pattern', 'network_method', 'network_request_body',
                         'network_body_match_type', 'network_mock_response',
                         'network_mock_passthrough', 'network_timeout',
                         'network_response_body', 'network_response_body_match_type',
                         'network_response_status']:
                if field in step:
                    new_step[field] = step[field]
            
            table.put_item(Item=new_step)
        
        # Clone variables
        try:
            variables_response = table.get_item(
                Key={
                    'pk': f'USECASE#{source_id}',
                    'sk': 'USECASE_VARIABLES'
                }
            )
            
            if 'Item' in variables_response:
                source_variables = variables_response['Item']
                if source_variables.get('variables'):
                    new_variables = {
                        'pk': f'USECASE#{new_usecase_id}',
                        'sk': 'USECASE_VARIABLES',
                        'variables': source_variables['variables'],
                        'created_at': now
                    }
                    table.put_item(Item=new_variables)
        except Exception as e:
            logger.warning(f"Error cloning variables: {str(e)}")
        
        # Clone headers
        try:
            headers_response = table.get_item(
                Key={
                    'pk': f'USECASE#{source_id}',
                    'sk': 'USECASE_HEADERS'
                }
            )
            
            if 'Item' in headers_response:
                new_headers = {**headers_response['Item']}
                new_headers['pk'] = f'USECASE#{new_usecase_id}'
                new_headers['created_at'] = now
                table.put_item(Item=new_headers)
        except Exception as e:
            logger.warning(f"Error cloning headers: {str(e)}")
        
        # Clone secrets (create empty placeholders)
        try:
            secret_prefix = f"{get_secret_prefix()}/usecase/{source_id}/"
            list_secrets_response = secrets_client.list_secrets(
                Filters=[
                    {'Key': 'tag-key', 'Values': ['usecase_id']},
                    {'Key': 'tag-value', 'Values': [source_id]}
                ]
            )
            
            for secret in list_secrets_response.get('SecretList', []):
                secret_name = secret.get('Name', '')
                if secret_name.startswith(secret_prefix):
                    secret_key = secret_name.replace(secret_prefix, '', 1)
                    description = secret.get('Description', '')
                    
                    new_secret_name = f"{get_secret_prefix()}/usecase/{new_usecase_id}/{secret_key}"
                    
                    # Save secret info to DynamoDB
                    secret_item = {
                        'pk': f'USECASE#{new_usecase_id}',
                        'sk': f'SECRET#{secret_key}',
                        'key': secret_key,
                        'secret_name': new_secret_name,
                        'description': description,
                        'created_at': now
                    }
                    table.put_item(Item=secret_item)
                    
                    # Create empty secret in AWS Secrets Manager
                    try:
                        secrets_client.create_secret(
                            Name=new_secret_name,
                            Description=f"Cloned secret: {description}",
                            SecretString='',
                            Tags=[
                                {'Key': 'usecase_id', 'Value': new_usecase_id}
                            ]
                        )
                    except ClientError as e:
                        logger.warning(f"Error creating secret {new_secret_name}: {str(e)}")
        except Exception as e:
            logger.warning(f"Error cloning secrets: {str(e)}")
        
        # Clone hooks
        try:
            hooks_response = table.get_item(
                Key={
                    'pk': f'USECASE#{source_id}',
                    'sk': 'HOOKS'
                }
            )
            
            if 'Item' in hooks_response:
                new_hooks = {**hooks_response['Item']}
                new_hooks['pk'] = f'USECASE#{new_usecase_id}'
                new_hooks['created_at'] = now
                table.put_item(Item=new_hooks)
        except Exception as e:
            logger.warning(f"Error cloning hooks: {str(e)}")
        
        logger.info(f"Successfully cloned usecase {source_id} to {new_usecase_id}")
        
        return create_response(200, {
            'success': True,
            'usecaseId': new_usecase_id,
            'message': 'Usecase cloned successfully'
        })
        
    except Exception as e:
        logger.error(f"Error cloning usecase: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
