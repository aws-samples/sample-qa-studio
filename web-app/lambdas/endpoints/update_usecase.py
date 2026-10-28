import json
import logging
import os
from typing import Any, Dict
import boto3
from utils import get_table_name, create_response, extract_user_identity
from permissions_repo import get_usecase_owner
from resource_auth import require_resource_access, usecase_from_path, authorize_target_app, is_studio_admin
from cache_invalidation import cleanup_cache_artifacts

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)




@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update a use case in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        usecase_id = event['pathParameters']['id']  # validated by usecase_from_path

        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        name = body.get('name')
        description = body.get('description')
        starting_url = body.get('starting_url')
        active = body.get('active')
        executing_region = body.get('executing_region', '').strip()
        # Use default region if empty
        if not executing_region:
            executing_region = os.environ.get('DEFAULT_REGION', 'us-east-1')
        model_id = body.get('model_id', '')
        tags = body.get('tags', [])
        enable_cache = body.get('enableCache')
        
        # Mobile fields
        test_platform = body.get('test_platform', '')
        platform = body.get('platform', '')
        app_package = body.get('app_package', '')
        app_activity = body.get('app_activity', '')
        bundle_id = body.get('bundle_id', '')
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Build update expression dynamically
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {
            '#name': 'name'
        }
        
        # Update these fields
        update_expression_parts.append('#name = :name')
        update_expression_parts.append('description = :description')
        update_expression_parts.append('starting_url = :starting_url')
        update_expression_parts.append('active = :active')
        update_expression_parts.append('executing_region = :executing_region')
        
        expression_attribute_values[':name'] = name
        expression_attribute_values[':description'] = description
        expression_attribute_values[':starting_url'] = starting_url
        expression_attribute_values[':active'] = active
        expression_attribute_values[':executing_region'] = executing_region
        
        # Update model_id if provided
        if model_id:
            update_expression_parts.append('model_id = :model_id')
            expression_attribute_values[':model_id'] = model_id
        
        # Update enable_cache if provided
        if enable_cache is not None:
            update_expression_parts.append('enable_cache = :enable_cache')
            expression_attribute_values[':enable_cache'] = enable_cache
        
        # Update mobile fields if provided
        if test_platform:
            update_expression_parts.append('test_platform = :test_platform')
            expression_attribute_values[':test_platform'] = test_platform
        
        if platform:
            update_expression_parts.append('platform = :platform')
            expression_attribute_values[':platform'] = platform
        
        mobile_optional_fields = {
            'app_package': app_package,
            'app_activity': app_activity,
            'bundle_id': bundle_id,
            'device_arn': body.get('device_arn', ''),
        }

        # Validate device_arn format if provided
        device_arn_value = mobile_optional_fields.get('device_arn', '')
        if device_arn_value and not device_arn_value.startswith('arn:aws:devicefarm:'):
            return create_response(400, {'error': 'Invalid device_arn format — must be a Device Farm device ARN'})
        for field_name, field_value in mobile_optional_fields.items():
            if field_value:
                update_expression_parts.append(f'{field_name} = :{field_name}')
                expression_attribute_values[f':{field_name}'] = field_value
        
        # Application association (N-5): moving a use case needs edit on the
        # target app too, and re-stamps owner_team_id from it. Only admins may
        # clear it (an app-less use case is admin-only).
        application_id = body.get('application_id')
        remove_parts = []
        if application_id is not None:
            current_app_id = (get_usecase_owner(usecase_id) or {}).get('application_id') or ''
            if not application_id:
                if current_app_id and not is_studio_admin(extract_user_identity(event)):
                    return create_response(403, {
                        'error': 'Forbidden',
                        'message': 'Only an admin can remove a use case from its application',
                    })
                update_expression_parts.append('application_id = :application_id')
                expression_attribute_values[':application_id'] = ''
                remove_parts.append('owner_team_id')
            elif application_id != current_app_id:
                target_owner, auth_err = authorize_target_app(event, application_id, 'edit')
                if auth_err:
                    return auth_err
                update_expression_parts.append('application_id = :application_id')
                expression_attribute_values[':application_id'] = application_id
                if target_owner:
                    update_expression_parts.append('owner_team_id = :owner_team_id')
                    expression_attribute_values[':owner_team_id'] = target_owner
                else:
                    remove_parts.append('owner_team_id')

        # Only update tags if provided and not empty (DynamoDB String Sets cannot be empty)
        if tags:
            update_expression_parts.append('tags = :tags')
            expression_attribute_values[':tags'] = set(tags)  # Convert to set for DynamoDB
        
        update_expression = 'SET ' + ', '.join(update_expression_parts)
        if remove_parts:
            update_expression += ' REMOVE ' + ', '.join(remove_parts)
        
        # Detect enable_cache true → false transition and trigger cleanup
        if enable_cache is not None:
            try:
                current_item_response = table.get_item(
                    Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'}
                )
                current_item = current_item_response.get('Item', {})
                previous_enable_cache = current_item.get('enable_cache')
                if previous_enable_cache is True and enable_cache is False:
                    s3_bucket = os.environ.get('S3_BUCKET', '')
                    cleanup_cache_artifacts(table, usecase_id, s3_bucket)
            except Exception as e:
                logger.warning(f"Cache cleanup: failed to read current usecase {usecase_id} for transition detection: {e}")

        # Update the use case
        table.update_item(
            Key={
                'pk': 'USECASES',
                'sk': f'USECASE#{usecase_id}'
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
        
        return create_response(200, {
            'status': 'usecase updated',
            'usecaseId': usecase_id
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error updating use case: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
