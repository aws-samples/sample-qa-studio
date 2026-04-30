import logging
import json
from typing import Any, Dict
from uuid import uuid4
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, get_current_timestamp, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a new usecase from a template.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created usecase
    """
    # Validate scopes - requires both template read and usecase write
    user_identity, error = require_scopes(event, ['api/templates.read', 'api/usecases.write'])
    if error:
        return error
    
    try:
        # Get template ID from path
        template_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'template ID')
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
        
        description = body.get('description', '')
        starting_url = body.get('starting_url', '')
        
        # Extract user info for created_by tracking
        user_email = user_identity.get('email') or user_identity.get('identity', 'unknown')
        user_sub = user_identity.get('sub', '')
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get template metadata
        template_response = table.get_item(
            Key={
                'pk': 'TEMPLATES',
                'sk': f'TEMPLATE#{template_id}'
            }
        )
        
        if 'Item' not in template_response:
            return create_response(404, {
                'success': False,
                'message': 'Template not found'
            })
        
        # Generate new usecase ID
        new_usecase_id = str(uuid4())
        now = get_current_timestamp()
        
        # Create new usecase with user-provided settings
        new_usecase = {
            'pk': 'USECASES',
            'sk': f'USECASE#{new_usecase_id}',
            'id': new_usecase_id,
            'name': name,
            'description': description,
            'starting_url': starting_url,
            'active': True,
            'region': 'eu-central-1',
            'tags': [],
            'created_at': now
        }
        
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
        
        # Copy steps from template
        logger.info(f"Copying steps from template {template_id} to usecase {new_usecase_id}")
        steps_response = table.query(
            KeyConditionExpression=Key('pk').eq(f'TEMPLATE#{template_id}') & Key('sk').begins_with('STEP#')
        )
        
        steps = steps_response.get('Items', [])
        steps.sort(key=lambda x: x.get('sort', 0))
        
        logger.info(f"Found {len(steps)} template steps")
        success_count = 0
        
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
                         'value_type',
                         'network_url_pattern', 'network_method', 'network_request_body',
                         'network_body_match_type', 'network_mock_response',
                         'network_mock_passthrough', 'network_timeout',
                         'network_response_body', 'network_response_body_match_type',
                         'network_response_status']:
                if field in step:
                    new_step[field] = step[field]
            
            try:
                table.put_item(Item=new_step)
                success_count += 1
                logger.info(f"Successfully saved step {step.get('sort')} (ID: {new_step_id})")
            except Exception as e:
                logger.error(f"Error saving step {step.get('sort')}: {str(e)}")
        
        logger.info(f"Successfully copied {success_count} out of {len(steps)} steps")
        
        # Copy variables from template
        try:
            variables_response = table.get_item(
                Key={
                    'pk': f'TEMPLATE#{template_id}',
                    'sk': 'VARIABLES'
                }
            )
            
            if 'Item' in variables_response:
                template_variables = variables_response['Item']
                if template_variables.get('variables'):
                    new_variables = {
                        'pk': f'USECASE#{new_usecase_id}',
                        'sk': 'USECASE_VARIABLES',
                        'variables': template_variables['variables'],
                        'created_at': now
                    }
                    table.put_item(Item=new_variables)
        except Exception as e:
            logger.warning(f"Error copying variables: {str(e)}")
        
        logger.info(f"Successfully created usecase {new_usecase_id} from template {template_id}")
        
        return create_response(200, {
            'success': True,
            'usecaseId': new_usecase_id,
            'message': 'Use case created from template successfully'
        })
        
    except Exception as e:
        logger.error(f"Error applying template: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
