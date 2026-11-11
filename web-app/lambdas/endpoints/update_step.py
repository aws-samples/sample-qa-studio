import lambda_init  # noqa: F401 — must be first import (dataset_models uses pydantic)
import json
import logging
from typing import Any, Dict, List
import boto3
from utils import get_table_name, create_response, validate_path_id
from resource_auth import require_resource_access, usecase_from_path
from repeat_validation import (
    REPEAT_STEP_TYPE,
    children_of,
    load_usecase_steps,
    validate_repeat_fields,
)
from dataset_models import DATASET_NOT_IN_APPLICATION_ERROR, missing_dataset_ids, usecase_application_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', usecase_from_path, scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update a step in Amazon DynamoDB.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response
    """
    try:
        # Get usecase ID and step ID from path parameters
        usecase_id = event['pathParameters']['id']  # validated by the resolver

        step_id, error = validate_path_id(event.get('pathParameters', {}).get('stepId'), 'step ID')
        if error:
            return error
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        instruction = body.get('instruction')
        step_type = body.get('step_type')
        
        if not instruction or not step_type:
            return create_response(400, {'error': 'Instruction and step_type are required'})
        
        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        repeat_columns = body.get('repeat_columns')
        repeat_rows = body.get('repeat_rows')
        dataset_id = body.get('dataset_id') or None
        parent_step_id = body.get('parent_step_id')

        # Repeat-related rules need the stored record and its siblings: the
        # merged (stored + patch) step is validated so a column change
        # re-validates stored rows, labels stay unique, and a repeat with
        # children cannot change type.
        candidate = {
            'id': step_id,
            'step_type': step_type,
            'instruction': instruction,
            'repeat_columns': repeat_columns,
            'repeat_rows': repeat_rows,
            'dataset_id': dataset_id,
            'parent_step_id': parent_step_id,
        }
        siblings = load_usecase_steps(table, usecase_id)
        existing = next((s for s in siblings if s.get('id') == step_id), None) or {}
        leaving_repeat = (
            existing.get('step_type') == REPEAT_STEP_TYPE and step_type != REPEAT_STEP_TYPE
        )
        if leaving_repeat and children_of(siblings, step_id):
            return create_response(400, {
                'error': 'cannot change the step type of a repeat step while it has children; '
                         'delete or move the children first'
            })
        merged = {**existing, **{k: v for k, v in candidate.items() if v is not None}}
        # The body names the dataset source: a reference replaces stored inline
        # rows and inline rows replace a stored reference.  A body carrying both
        # is rejected by the validator below, never silently preferred.
        dropped_fields: List[str] = []
        if leaving_repeat:
            dropped_fields = ['repeat_columns', 'repeat_rows', 'dataset_id']
        elif dataset_id is not None and repeat_columns is None and repeat_rows is None:
            dropped_fields = ['repeat_columns', 'repeat_rows']
        elif dataset_id is None and (repeat_columns is not None or repeat_rows is not None):
            dropped_fields = ['dataset_id']
        for field in dropped_fields:
            merged.pop(field, None)
        repeat_errors = validate_repeat_fields(merged, siblings)
        if repeat_errors:
            return create_response(400, {'error': '; '.join(repeat_errors)})
        if dataset_id is not None:
            app_id = usecase_application_id(table, usecase_id)
            if missing_dataset_ids(table, app_id, [dataset_id]):
                return create_response(400, {'error': DATASET_NOT_IN_APPLICATION_ERROR})
        
        # Build dynamic update expression
        update_expression_parts = ['instruction = :instruction', 'step_type = :step_type']
        expression_attribute_values = {
            ':instruction': instruction,
            ':step_type': step_type
        }
        
        # Add optional fields if provided
        optional_fields = {
            'secret_key': body.get('secret_key'),
            'validation_type': body.get('validation_type'),
            'validation_operator': body.get('validation_operator'),
            'validation_value': body.get('validation_value'),
            'capture_variable': body.get('capture_variable'),
            'assertion_variable': body.get('assertion_variable'),
            'value_type': body.get('value_type'),
            'value_format': body.get('value_format'),
            'enable_advanced_click_types': body.get('enable_advanced_click_types'),
            'value_source': body.get('value_source'),
            'browser_action': body.get('browser_action'),
            'browser_args': body.get('browser_args'),
            'transform_operation': body.get('transform_operation'),
            'transform_args': body.get('transform_args'),
            'network_url_pattern': body.get('network_url_pattern'),
            'network_method': body.get('network_method'),
            'network_request_body': body.get('network_request_body'),
            'network_body_match_type': body.get('network_body_match_type'),
            'network_mock_response': body.get('network_mock_response'),
            'network_mock_passthrough': body.get('network_mock_passthrough'),
            'network_timeout': body.get('network_timeout'),
            'network_response_body': body.get('network_response_body'),
            'network_response_body_match_type': body.get('network_response_body_match_type'),
            'network_response_status': body.get('network_response_status'),
            'repeat_columns': repeat_columns,
            'repeat_rows': repeat_rows,
            'dataset_id': dataset_id,
            'parent_step_id': parent_step_id,
        }
        
        for field_name, field_value in optional_fields.items():
            if field_value is not None and field_value != '':
                update_expression_parts.append(f'{field_name} = :{field_name}')
                expression_attribute_values[f':{field_name}'] = field_value
        
        update_expression = 'SET ' + ', '.join(update_expression_parts)
        if dropped_fields:
            # Stale dataset source (or any dataset on a non-repeat step) is
            # meaningless; drop it with the same write.
            update_expression += ' REMOVE ' + ', '.join(dropped_fields)
        
        # Update the step
        table.update_item(
            Key={
                'pk': f'USECASE#{usecase_id}',
                'sk': f'STEP#{step_id}'
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values
        )
        
        return create_response(200, {
            'status': 'step updated',
            'stepId': step_id
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        logger.error(f"Error updating step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
