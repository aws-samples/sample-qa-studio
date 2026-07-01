import json
import boto3
from utils import create_response, get_table_name, require_scopes, validate_path_id

dynamodb = boto3.client('dynamodb')

# Fields the CLI runner may clear on the step-definition record during
# cache-cleanup after a failed trajectory replay (R-API-6).  The allow-list
# is closed: anything outside it is rejected to prevent the endpoint from
# doubling as an arbitrary-attribute deleter.
_ALLOWED_CLEAR_FIELDS = {
    'trajectory_s3_key',
    'trajectory_last_updated',
    'cached_steps',
    'cache_last_updated',
}


def handler(event, context):
    """
    Update the status of an individual execution step.
    Used by CI/CD runner to report step progress during test execution.
    
    Path Parameters:
    - id: Usecase ID
    - executionId: Execution ID
    - stepId: Step ID to update
    
    Request Body:
    - status: Step status (pending, running, completed, failed, skipped, success)
    - started_at: ISO8601 timestamp when step started (optional)
    - completed_at: ISO8601 timestamp when step completed (optional)
    - error_message: Error message for failed steps (optional)
    - actual_value: Actual value from validation/retrieve_value steps (optional)
    - act_id: Nova Act action ID for trace linking (optional)
    - logs: Step execution logs (optional)
    
    Returns:
    - 200: Step status updated successfully
    - 400: Invalid status value or missing required fields
    - 401: Unauthorized
    - 403: Insufficient permissions (requires api/executions.write scope)
    - 404: Execution or step not found
    - 500: Internal server error
    """
    # Validate scope authorization (requires api/executions.write or admin)
    user_identity, error_response = require_scopes(event, ['api/executions.write'])
    if error_response:
        return error_response
    
    print(f"Step status update requested by: {user_identity['identity']} (type: {user_identity['identity_type']})")
    
    # Parse path parameters
    usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'usecase ID')
    if error:
        return error
    execution_id, error = validate_path_id(event.get('pathParameters', {}).get('executionId'), 'execution ID')
    if error:
        return error
    step_id, error = validate_path_id(event.get('pathParameters', {}).get('stepId'), 'step ID')
    if error:
        return error
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})
    
    status = body.get('status')
    started_at = body.get('started_at')
    completed_at = body.get('completed_at')
    error_message = body.get('error_message')
    actual_value = body.get('actual_value')
    act_id = body.get('act_id')
    logs = body.get('logs')
    clear_cache_fields = body.get('clear_cache_fields')

    # Validate clear_cache_fields shape + allow-list before any writes.
    if clear_cache_fields is not None:
        if not isinstance(clear_cache_fields, list):
            return create_response(
                400, {'error': 'clear_cache_fields must be a list of strings'},
            )
        if not all(isinstance(f, str) for f in clear_cache_fields):
            return create_response(
                400, {'error': 'clear_cache_fields must be a list of strings'},
            )
        unknown = [f for f in clear_cache_fields if f not in _ALLOWED_CLEAR_FIELDS]
        if unknown:
            return create_response(
                400,
                {
                    'error': (
                        'clear_cache_fields contains unknown fields: '
                        + ', '.join(sorted(unknown))
                    ),
                },
            )
    
    # Validate required fields
    if not status:
        return create_response(400, {'error': 'Missing required field: status'})
    
    # Validate status value
    valid_statuses = ['pending', 'running', 'completed', 'failed', 'skipped', 'success']
    if status not in valid_statuses:
        return create_response(400, {
            'error': f'Invalid status: {status}. Valid values: {", ".join(valid_statuses)}'
        })
    
    table_name = get_table_name()
    
    try:
        # Verify execution exists
        execution_response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            }
        )
        
        if 'Item' not in execution_response:
            return create_response(404, {'error': 'Execution not found'})
        
        # Verify step exists
        step_response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': f'EXECUTION_STEP#{step_id}'}
            }
        )
        
        if 'Item' not in step_response:
            return create_response(404, {'error': 'Step not found'})
        
        # Build update expression dynamically based on provided fields
        update_expression = 'SET #status = :status'
        expression_attribute_names = {'#status': 'status'}
        expression_attribute_values = {':status': {'S': status}}
        
        if started_at:
            update_expression += ', started_at = :started_at'
            expression_attribute_values[':started_at'] = {'S': started_at}
        
        if completed_at:
            update_expression += ', completed_at = :completed_at'
            expression_attribute_values[':completed_at'] = {'S': completed_at}
        
        if error_message:
            update_expression += ', error_message = :error_message'
            expression_attribute_values[':error_message'] = {'S': error_message}
        
        if actual_value:
            update_expression += ', actual_value = :actual_value'
            expression_attribute_values[':actual_value'] = {'S': actual_value}
        
        if act_id:
            update_expression += ', act_id = :act_id'
            expression_attribute_values[':act_id'] = {'S': act_id}
        
        if logs:
            update_expression += ', #logs = :logs'
            expression_attribute_names['#logs'] = 'logs'
            expression_attribute_values[':logs'] = {'S': logs}
        
        # Update step status in DynamoDB
        dynamodb.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': f'EXECUTION_STEP#{step_id}'}
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )

        # Clear stale cache fields on the step-definition record when
        # requested. Cache fields live on ``USECASE#{uc}/STEP#{step}``
        # (the step's canonical record), NOT on the execution-step record
        # we just updated. See R-API-6 in the spec — used by the runner
        # when trajectory replay failed and the pointer is now stale.
        # Best-effort: a DynamoDB failure here does not fail the status
        # update, which is the primary action the caller asked for.
        if clear_cache_fields:
            # De-duplicate while preserving order for a deterministic
            # REMOVE expression.
            seen = []
            for field in clear_cache_fields:
                if field not in seen:
                    seen.append(field)
            # The step_definition_id identifies the canonical STEP record.
            # The URL's step_id is the execution-step UUID which is different.
            # Fall back to step_id for backward compatibility with older
            # CLI versions that don't send step_definition_id.
            definition_id = body.get('step_definition_id') or step_id
            try:
                dynamodb.update_item(
                    TableName=table_name,
                    Key={
                        'pk': {'S': f'USECASE#{usecase_id}'},
                        'sk': {'S': f'STEP#{definition_id}'},
                    },
                    UpdateExpression='REMOVE ' + ', '.join(seen),
                )
            except Exception as cleanup_exc:  # noqa: BLE001 — best-effort
                print(
                    f'Failed to clear cache fields {seen} for step {definition_id}: '
                    f'{cleanup_exc}'
                )
        
        print(f'Updated step {step_id} status to {status} for execution {execution_id}')
        
        return create_response(200, {
            'success': True,
            'step_id': step_id,
            'status': status
        })
    
    except Exception as e:
        print(f'Error updating step status: {str(e)}')
        return create_response(500, {'error': 'Failed to update step status'})
