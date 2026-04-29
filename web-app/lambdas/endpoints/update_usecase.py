import json
import logging
import os
import re
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import get_table_name, create_response, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _clear_step_cache_fields(table, usecase_id: str) -> None:
    """Query all STEP records for a use case and REMOVE cache fields.

    Each individual step update is wrapped in try/except so that a failure
    on one step does not prevent cleanup of the remaining steps.
    Handles DynamoDB pagination for large step sets.

    Args:
        table: DynamoDB table resource
        usecase_id: The use case ID
    """
    try:
        query_kwargs = {
            'KeyConditionExpression': Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('STEP#'),
        }
        while True:
            response = table.query(**query_kwargs)
            items = response.get('Items', [])
            for item in items:
                step_sk = item['sk']
                try:
                    table.update_item(
                        Key={'pk': f'USECASE#{usecase_id}', 'sk': step_sk},
                        UpdateExpression='REMOVE cached_steps, cache_last_updated, trajectory_s3_key, trajectory_last_updated',
                    )
                except Exception as e:
                    logger.warning(f"Cache cleanup: failed to remove cache fields for step {step_sk} in usecase {usecase_id}: {e}")

            # Handle pagination
            last_key = response.get('LastEvaluatedKey')
            if last_key:
                query_kwargs['ExclusiveStartKey'] = last_key
            else:
                break
    except Exception as e:
        logger.warning(f"Cache cleanup: failed to query steps for usecase {usecase_id}: {e}")


def _delete_trajectory_files(s3_client, s3_bucket: str, usecase_id: str) -> None:
    """Delete all trajectory files from S3 for a use case.

    Uses list_objects_v2 + delete_objects for batch deletion.
    Filters to trajectory path pattern: {usecase_id}/*/trajectories/*.json

    Args:
        s3_client: boto3 S3 client
        s3_bucket: S3 bucket name
        usecase_id: The use case ID
    """
    try:
        trajectory_pattern = re.compile(
            rf'^{re.escape(usecase_id)}/[^/]+/trajectories/[^/]+\.json$'
        )
        continuation_token = None

        while True:
            list_kwargs = {
                'Bucket': s3_bucket,
                'Prefix': f'{usecase_id}/',
            }
            if continuation_token:
                list_kwargs['ContinuationToken'] = continuation_token

            response = s3_client.list_objects_v2(**list_kwargs)
            contents = response.get('Contents', [])

            # Filter to trajectory files only
            keys_to_delete = [
                {'Key': obj['Key']}
                for obj in contents
                if trajectory_pattern.match(obj['Key'])
            ]

            # Batch delete up to 1000 at a time
            while keys_to_delete:
                batch = keys_to_delete[:1000]
                keys_to_delete = keys_to_delete[1000:]
                try:
                    s3_client.delete_objects(
                        Bucket=s3_bucket,
                        Delete={'Objects': batch, 'Quiet': True},
                    )
                except Exception as e:
                    logger.warning(f"Cache cleanup: failed to delete trajectory files batch for usecase {usecase_id}: {e}")

            if response.get('IsTruncated'):
                continuation_token = response.get('NextContinuationToken')
            else:
                break
    except Exception as e:
        logger.warning(f"Cache cleanup: failed to delete trajectory files for usecase {usecase_id}: {e}")


def _cleanup_cache_artifacts(table, usecase_id: str, s3_bucket: str) -> None:
    """Remove cache fields from all STEP records and delete trajectory files from S3.

    Non-fatal: logs warnings on individual failures, never raises.

    Args:
        table: DynamoDB table resource
        usecase_id: The use case ID being updated
        s3_bucket: S3 bucket name for trajectory file deletion
    """
    try:
        _clear_step_cache_fields(table, usecase_id)

        if s3_bucket:
            s3_client = boto3.client('s3')
            _delete_trajectory_files(s3_client, s3_bucket, usecase_id)
    except Exception as e:
        logger.warning(f"Cache cleanup: unexpected error for usecase {usecase_id}: {e}")


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
        # Validate scope (requires usecases.write or admin)
        user_identity, error_response = require_scopes(event, ['api/usecases.write'])
        if error_response:
            return error_response
        
        # Get use case ID from path parameters
        usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
        if error:
            return error
        
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
        
        # Only update tags if provided and not empty (DynamoDB String Sets cannot be empty)
        if tags:
            update_expression_parts.append('tags = :tags')
            expression_attribute_values[':tags'] = set(tags)  # Convert to set for DynamoDB
        
        update_expression = 'SET ' + ', '.join(update_expression_parts)
        
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
                    _cleanup_cache_artifacts(table, usecase_id, s3_bucket)
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
