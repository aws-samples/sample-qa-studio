import lambda_init  # noqa: F401 — must be first import (dataset_models uses pydantic)
import json
import logging
from typing import Any, Dict
from uuid import uuid4
import boto3
from utils import get_table_name, create_response, get_current_timestamp
from resource_auth import require_resource_access, usecase_from_path
from repeat_validation import (
    has_dataset_reference,
    load_usecase_steps,
    needs_sibling_validation,
    validate_repeat_fields,
)
from dataset_models import DATASET_NOT_IN_APPLICATION_ERROR, missing_dataset_ids, usecase_application_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to create a step for a use case in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with created step
    """
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # The step belongs to the use case in the path (authorized by the
        # resolver); a different body usecaseId would write to another use case.
        usecase_id = event['pathParameters']['id']
        if body.get('usecaseId') not in (None, usecase_id):
            return create_response(400, {'error': 'usecaseId does not match the path'})
        sort = body.get('sort')
        instruction = body.get('instruction')
        step_type = body.get('step_type', 'navigation')  # Default to navigation
        secret_key = body.get('secret_key', '')
        validation_type = body.get('validation_type', '')
        validation_operator = body.get('validation_operator', '')
        validation_value = body.get('validation_value', '')
        capture_variable = body.get('capture_variable', '')
        assertion_variable = body.get('assertion_variable', '')
        value_type = body.get('value_type', '')
        value_format = body.get('value_format', '')
        enable_advanced_click_types = body.get('enable_advanced_click_types', False)
        value_source = body.get('value_source', '')
        network_url_pattern = body.get('network_url_pattern')
        network_method = body.get('network_method')
        network_request_body = body.get('network_request_body')
        network_body_match_type = body.get('network_body_match_type')
        network_mock_response = body.get('network_mock_response')
        network_mock_passthrough = body.get('network_mock_passthrough', False)
        network_timeout = body.get('network_timeout')
        network_response_body = body.get('network_response_body')
        network_response_body_match_type = body.get('network_response_body_match_type')
        network_response_status = body.get('network_response_status')
        repeat_columns = body.get('repeat_columns')
        repeat_rows = body.get('repeat_rows')
        dataset_id = body.get('dataset_id')
        parent_step_id = body.get('parent_step_id')
        
        if not usecase_id or sort is None or not instruction:
            return create_response(400, {'error': 'Missing required fields'})
        
        # Generate UUID and timestamp
        step_id = str(uuid4())
        now = get_current_timestamp()
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        # Repeat steps / children are validated against their siblings
        # (label uniqueness, parent exists and is a top-level repeat).
        candidate = {
            'id': step_id,
            'step_type': step_type,
            'instruction': instruction,
            'repeat_columns': repeat_columns,
            'repeat_rows': repeat_rows,
            'dataset_id': dataset_id,
            'parent_step_id': parent_step_id,
        }
        if needs_sibling_validation(candidate):
            siblings = load_usecase_steps(table, usecase_id)
            repeat_errors = validate_repeat_fields(candidate, siblings)
            if repeat_errors:
                return create_response(400, {'error': '; '.join(repeat_errors)})
        # A dataset reference must point at a dataset of the use case's application.
        if has_dataset_reference(candidate):
            app_id = usecase_application_id(table, usecase_id)
            if missing_dataset_ids(table, app_id, [dataset_id]):
                return create_response(400, {'error': DATASET_NOT_IN_APPLICATION_ERROR})
        
        # Create step item
        step = {
            'pk': f'USECASE#{usecase_id}',
            'sk': f'STEP#{step_id}',
            'id': step_id,
            'sort': sort,
            'instruction': instruction,
            'step_type': step_type,
            'secret_key': secret_key,
            'validation_type': validation_type,
            'validation_operator': validation_operator,
            'validation_value': validation_value,
            'capture_variable': capture_variable,
            'assertion_variable': assertion_variable,
            'value_type': value_type,
            'value_format': value_format,
            'enable_advanced_click_types': enable_advanced_click_types,
            'value_source': value_source,
            'created_at': now
        }

        # Add network_assertion fields when provided (kept off the record otherwise
        # so existing step types are unaffected).
        for key, value in (
            ('network_url_pattern', network_url_pattern),
            ('network_method', network_method),
            ('network_request_body', network_request_body),
            ('network_body_match_type', network_body_match_type),
            ('network_mock_response', network_mock_response),
            ('network_timeout', network_timeout),
            ('network_response_body', network_response_body),
            ('network_response_body_match_type', network_response_body_match_type),
            ('network_response_status', network_response_status),
        ):
            if value is not None:
                step[key] = value
        if network_mock_passthrough:
            step['network_mock_passthrough'] = True

        # Repeat dataset (inline rows or application dataset reference) /
        # parent pointer: kept off the record unless provided.
        for key, value in (
            ('repeat_columns', repeat_columns),
            ('repeat_rows', repeat_rows),
            ('dataset_id', dataset_id or None),
            ('parent_step_id', parent_step_id or None),
        ):
            if value is not None:
                step[key] = value
        
        # Add browser step fields if present
        for field in ['browser_action', 'browser_args', 'transform_operation', 'transform_args']:
            if body.get(field):
                step[field] = body[field]
        
        # Put item in DynamoDB
        table.put_item(Item=step)
        
        return create_response(201, step)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error creating step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
