import logging
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, get_secret_prefix, get_current_timestamp

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to import a usecase from export data.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with import result
    """
    try:
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Validate export version
        export_version = body.get('exportVersion')
        if export_version != '1.0':
            return create_response(400, {
                'success': False,
                'message': 'Unsupported export version'
            })
        
        # Extract user claims for created_by tracking
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        claims = authorizer.get('claims', {})
        user_email = claims.get('email', '')
        user_sub = claims.get('sub', '')
        
        if not user_email:
            return create_response(401, {'error': 'Unauthorized'})
        
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        secrets_client = boto3.client('secretsmanager')
        
        # Generate new IDs
        new_usecase_id = str(uuid4())
        now = get_current_timestamp()
        
        # Extract import data
        usecase_data = body.get('usecase', {})
        steps_data = body.get('steps', [])
        variables_data = body.get('variables', [])
        secrets_data = body.get('secrets', [])
        hooks_data = body.get('hooks')
        
        # Create new usecase with proper pk/sk
        usecase_tags = usecase_data.get('tags', [])
        # Add "imported" tag if not already present
        if 'imported' not in usecase_tags:
            usecase_tags.append('imported')
        
        new_usecase = {
            'pk': 'USECASES',
            'sk': f'USECASE#{new_usecase_id}',
            'id': new_usecase_id,
            'name': usecase_data.get('name', ''),
            'description': usecase_data.get('description', ''),
            'starting_url': usecase_data.get('starting_url', ''),
            'active': usecase_data.get('active', False),
            'executing_region': usecase_data.get('executing_region', ''),
            'tags': usecase_tags,
            'created_at': now
        }
        
        # Save usecase
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
        
        # Save steps with proper pk/sk recreation
        for i, step in enumerate(steps_data):
            new_step_id = str(uuid4())
            new_step = {
                'pk': f'USECASE#{new_usecase_id}',
                'sk': f'STEP#{new_step_id}',
                'sort': i + 1,  # Reorder sequentially
                'id': new_step_id,
                'instruction': step.get('instruction', ''),
                'step_type': step.get('step_type', ''),
                'created_at': now
            }
            
            # Add optional fields if present
            if step.get('secret_key'):
                new_step['secret_key'] = step['secret_key']
            if step.get('capture_variable'):
                new_step['capture_variable'] = step['capture_variable']
            if step.get('validation_type'):
                new_step['validation_type'] = step['validation_type']
            if step.get('validation_operator'):
                new_step['validation_operator'] = step['validation_operator']
            if step.get('validation_value'):
                new_step['validation_value'] = step['validation_value']
            if step.get('assertion_variable'):
                new_step['assertion_variable'] = step['assertion_variable']
            if step.get('value_step'):
                new_step['value_step'] = step['value_step']
            if step.get('value_type'):
                new_step['value_type'] = step['value_type']
            
            try:
                table.put_item(Item=new_step)
            except Exception as e:
                logger.error(f"Error saving step: {str(e)}")
        
        # Save variables
        if variables_data:
            usecase_variables = {
                'pk': f'USECASE#{new_usecase_id}',
                'sk': 'USECASE_VARIABLES',
                'variables': variables_data,
                'created_at': now
            }
            table.put_item(Item=usecase_variables)
        
        # Save secret placeholders (without values)
        missing_secrets = []
        for secret in secrets_data:
            secret_key = secret.get('key', '')
            secret_name = f"{get_secret_prefix()}/{new_usecase_id}/{secret_key}"
            
            # Save secret info to DynamoDB
            secret_item = {
                'pk': f'USECASE#{new_usecase_id}',
                'sk': f'SECRET#{secret_key}',
                'key': secret_key,
                'secret_name': secret_name,
                'description': secret.get('description', ''),
                'created_at': now
            }
            
            try:
                table.put_item(Item=secret_item)
            except Exception as e:
                logger.error(f"Error saving secret info: {str(e)}")
            
            # Create empty secret in AWS Secrets Manager
            try:
                secrets_client.create_secret(
                    Name=secret_name,
                    Description=f"Imported secret: {secret.get('description', '')}",
                    SecretString=''  # Empty value - needs to be configured
                )
            except Exception as e:
                logger.error(f"Error creating secret in AWS: {str(e)}")
            
            missing_secrets.append(secret_key)
        
        # Save hooks
        if hooks_data:
            hooks_item = {
                'pk': f'USECASE#{new_usecase_id}',
                'sk': 'HOOKS',
                'before_script': hooks_data.get('beforeScript', ''),
                'after_script': hooks_data.get('afterScript', ''),
                'created_at': now
            }
            
            try:
                table.put_item(Item=hooks_item)
            except Exception as e:
                logger.error(f"Error saving hooks: {str(e)}")
        
        # Create response
        response_data = {
            'success': True,
            'usecaseId': new_usecase_id,
            'message': 'Usecase imported successfully'
        }
        
        if missing_secrets:
            response_data['missingSecrets'] = missing_secrets
        
        return create_response(200, response_data)
        
    except Exception as e:
        logger.error(f"Error importing usecase: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
