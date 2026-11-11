"""
AWS Lambda function for updating execution status.

This endpoint allows CI/CD runners to update execution status as tests progress.

Endpoint: PATCH /api/usecases/{id}/executions/{execution_id}/status
"""
import lambda_init  # noqa: F401 — must be first import (execution_transitions uses pydantic from dependencies/)
import json
import boto3
from typing import Dict, Any

from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    extract_user_identity,
    validate_path_id)
from resource_auth import require_resource_access, execution_from_path
from execution_transitions import (
    TERMINAL_STATUSES,
    finalize_terminal_transition,
    publish_status_changed,
)
# Not called here (the shared module calls it); re-exported only because
# test_update_execution_status.py patches ``update_execution_status.cleanup_cache_artifacts``.
from execution_transitions import cleanup_cache_artifacts  # noqa: F401

dynamodb = boto3.client('dynamodb')
eventbridge = boto3.client('events')


@require_resource_access('execute', execution_from_path, scopes=['api/executions.write'], allow_worker=True)
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Update execution status.
    
    Path Parameters:
        id: Usecase UUID
        execution_id: Execution UUID
    
    Request Body:
        status: New status (pending, running, completed, failed, success)
        error_message: Optional error message for failed executions
    
    Returns:
        200: Status updated successfully (or the record already carries this
             terminal status — idempotent no-op, nothing written or counted)
        400: Invalid status value
        403: Insufficient permissions
        404: Execution not found
        409: Execution is already in a different terminal state; nothing written
        500: Internal server error
    """
    user_identity = extract_user_identity(event)
    
    print(f"Execution status update requested by identity type: {user_identity['identity_type']}")
    
    # Parse path parameters
    usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
    if error:
        return error

    execution_id, error = validate_path_id(event.get('pathParameters', {}).get('executionId'), 'execution ID')
    if error:
        return error
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})
    
    # Validate status
    status = body.get('status')
    valid_statuses = ['pending', 'running', 'completed', 'failed', 'success']
    
    if not status:
        return create_response(400, {'error': 'Missing status field'})
    
    if status not in valid_statuses:
        return create_response(400, {
            'error': 'Invalid status',
            'message': f'Status must be one of: {", ".join(valid_statuses)}'
        })
    
    error_message = body.get('error_message')
    nova_session_id = body.get('nova_session_id')
    
    print(f'Updating execution {execution_id} status to: {status}')
    
    table_name = get_table_name()
    
    try:
        # Check if execution exists
        get_response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            }
        )
        
        if 'Item' not in get_response:
            return create_response(404, {
                'error': 'Execution not found',
                'message': f'No execution found with ID: {execution_id}'
            })

        # Terminal-state guard: never overwrite a finished execution.
        current_status = get_response['Item'].get('status', {}).get('S', '')
        if current_status in TERMINAL_STATUSES:
            if status == current_status:
                print(f'Execution {execution_id} already {current_status}; idempotent no-op')
                return create_response(200, {
                    'execution_id': execution_id,
                    'status': status,
                    'updated_at': get_current_timestamp()
                })
            print(f'Rejecting status {status} for execution {execution_id}: already terminal ({current_status})')
            return create_response(409, {
                'error': 'execution already terminal',
                'status': current_status
            })
        
        # Build update expression
        update_expr = 'SET #status = :status, updated_at = :updated_at'
        expr_attr_names = {'#status': 'status'}
        expr_attr_values = {
            ':status': {'S': status},
            ':updated_at': {'S': get_current_timestamp()}
        }
        
        # Add timestamps based on status
        if status == 'running':
            update_expr += ', started_at = :started_at'
            expr_attr_values[':started_at'] = {'S': get_current_timestamp()}
        elif status in ['completed', 'failed', 'success']:
            update_expr += ', completed_at = :completed_at'
            expr_attr_values[':completed_at'] = {'S': get_current_timestamp()}
        
        # Add error message if provided
        if error_message:
            update_expr += ', error_message = :error_message'
            expr_attr_values[':error_message'] = {'S': error_message}
        
        # Add nova_session_id if provided and non-empty
        if nova_session_id:
            update_expr += ', nova_session_id = :nova_session_id'
            expr_attr_values[':nova_session_id'] = {'S': nova_session_id}
        
        # Update execution status
        dynamodb.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            },
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
        
        print(f'Updated execution {execution_id} to status: {status}')

        if status in TERMINAL_STATUSES:
            # Tracking-record delete, EventBridge event, cache wipe on
            # ``failed``, suite counters/completion/summary — the one shared
            # implementation (the reconciler takes the same path).
            finalize_terminal_transition(
                dynamodb, eventbridge, table_name, usecase_id, execution_id, status,
                get_response['Item'], error_message=error_message,
            )
        else:
            publish_status_changed(eventbridge, usecase_id, execution_id, status, error_message)

        return create_response(200, {
            'execution_id': execution_id,
            'status': status,
            'updated_at': get_current_timestamp()
        })
        
    except Exception as e:
        print(f'Error updating execution status: {str(e)}')
        import traceback
        traceback.print_exc()
        return create_response(500, {
            'error': 'Failed to update execution status',
            'message': str(e)
        })
