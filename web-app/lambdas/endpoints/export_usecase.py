import logging
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, get_secret_prefix, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def convert_dynamodb_types(obj):
    """
    Recursively convert DynamoDB types (sets, Decimals) to JSON-serializable types.
    
    Args:
        obj: Object to convert (can be dict, list, set, Decimal, or primitive)
        
    Returns:
        Object with all DynamoDB types converted to JSON-serializable types
    """
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, Decimal):
        # Convert Decimal to int if it's a whole number, otherwise to float
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_dynamodb_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_dynamodb_types(item) for item in obj]
    else:
        return obj


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to export a usecase with all its configuration.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with export data
    """
    try:
        # Validate scope authorization
        user_identity, error = require_scopes(event, ['api/usecases.read'])
        if error:
            return error
        
        # Get usecase ID from path
        path_params = event.get('pathParameters', {})
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        secrets_client = boto3.client('secretsmanager')
        
        # Get usecase
        usecase_response = table.get_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}'
            }
        )
        
        if 'Item' not in usecase_response:
            return create_response(404, {'error': 'Usecase not found'})
        
        usecase = usecase_response['Item']
        
        # Get steps
        steps_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('STEP#')
        )
        
        steps = []
        for item in steps_response.get('Items', []):
            # Convert to clean export format (no IDs)
            step_export = {
                'sort': item.get('sort', 0),
                'instruction': item.get('instruction', ''),
                'step_type': item.get('step_type', '')
            }
            
            # Add optional fields if present
            if item.get('secret_key'):
                step_export['secret_key'] = item['secret_key']
            if item.get('capture_variable'):
                step_export['capture_variable'] = item['capture_variable']
            if item.get('validation_type'):
                step_export['validation_type'] = item['validation_type']
            if item.get('validation_operator'):
                step_export['validation_operator'] = item['validation_operator']
            if item.get('validation_value'):
                step_export['validation_value'] = item['validation_value']
            if item.get('assertion_variable'):
                step_export['assertion_variable'] = item['assertion_variable']
            if item.get('value_step'):
                step_export['value_step'] = item['value_step']
            if item.get('value_type'):
                step_export['value_type'] = item['value_type']
            
            steps.append(step_export)
        
        # Sort steps by sort property
        steps.sort(key=lambda x: x.get('sort', 0))
        
        # Get variables - initialize as empty list to avoid null in JSON
        variables = []
        try:
            variables_response = table.get_item(
                Key={
                    'pk': f'USECASE#{usecase_id}',
                    'sk': 'USECASE_VARIABLES'
                }
            )
            
            if 'Item' in variables_response:
                variables = variables_response['Item'].get('variables', [])
                logger.info(f"Found {len(variables)} variables for usecase {usecase_id}")
            else:
                logger.info(f"No variables found for usecase {usecase_id}")
        except Exception as e:
            logger.warning(f"Error getting variables: {str(e)}")
        
        # Get secrets from AWS Secrets Manager (without values) - initialize as empty list
        secrets = []
        secret_prefix = f"{get_secret_prefix()}/usecase/{usecase_id}/"
        
        try:
            # List secrets with the usecase tag (same approach as get_usecase_secrets)
            list_secrets_response = secrets_client.list_secrets(
                Filters=[
                    {
                        'Key': 'tag-key',
                        'Values': ['usecase_id']
                    },
                    {
                        'Key': 'tag-value',
                        'Values': [usecase_id]
                    }
                ]
            )
            
            logger.info(f"Found {len(list_secrets_response.get('SecretList', []))} secrets for usecase {usecase_id}")
            
            for secret in list_secrets_response.get('SecretList', []):
                secret_name = secret.get('Name', '')
                if secret_name.startswith(secret_prefix):
                    # Extract the secret key from the full name (remove prefix)
                    secret_key = secret_name.replace(secret_prefix, '', 1)
                    description = secret.get('Description', '')
                    
                    secrets.append({
                        'key': secret_key,
                        'value': None,  # Do not export actual secret values
                        'placeholder': f"Required: {description}"
                    })
        except Exception as e:
            logger.warning(f"Error listing secrets: {str(e)}")
        
        # Get hooks
        hooks = None
        try:
            hooks_response = table.get_item(
                Key={
                    'pk': f'USECASE#{usecase_id}',
                    'sk': 'HOOKS'
                }
            )
            
            if 'Item' in hooks_response:
                before_script = hooks_response['Item'].get('before_script', '')
                after_script = hooks_response['Item'].get('after_script', '')
                
                if before_script or after_script:
                    hooks = {
                        'beforeScript': before_script,
                        'afterScript': after_script
                    }
        except Exception as e:
            logger.warning(f"Error getting hooks: {str(e)}")
        
        # Convert usecase to clean export format (no IDs or timestamps)
        usecase_export = {
            'name': usecase.get('name', ''),
            'description': usecase.get('description', ''),
            'starting_url': usecase.get('starting_url', ''),
            'active': usecase.get('active', False),
            'executing_region': usecase.get('executing_region', ''),
            'tags': list(usecase.get('tags', [])) if usecase.get('tags') else [],
            'model_id': usecase.get('model_id', ''),
            'test_platform': usecase.get('test_platform', 'web'),
        }

        # Add mobile-specific fields if present
        mobile_fields = ['platform', 'app_package', 'app_activity', 'bundle_id', 'device_arn']
        for field in mobile_fields:
            val = usecase.get(field, '')
            if val:
                usecase_export[field] = val
        
        # Create export data
        export_data = {
            'exportVersion': '1.0',
            'exportedAt': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'usecase': usecase_export,
            'steps': steps,
            'variables': variables,
            'secrets': secrets
        }
        
        # Add hooks if present
        if hooks:
            export_data['hooks'] = hooks
        
        # Convert any DynamoDB types (sets, Decimals) to JSON-serializable types
        export_data = convert_dynamodb_types(export_data)
        
        # Create response with download headers
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Content-Disposition': f'attachment; filename="usecase-{usecase_id}-export.json"'
            },
            'body': json.dumps(export_data)
        }
        
    except Exception as e:
        logger.error(f"Error exporting usecase: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
