import json
import boto3
from utils import create_response, get_table_name, require_scopes

dynamodb = boto3.client('dynamodb')


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
    usecase_id = event.get('pathParameters', {}).get('id')
    execution_id = event.get('pathParameters', {}).get('executionId')
    step_id = event.get('pathParameters', {}).get('stepId')
    
    if not usecase_id or not execution_id or not step_id:
        return create_response(400, {'error': 'Missing required path parameters'})
    
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
        
        print(f'Updated step {step_id} status to {status} for execution {execution_id}')
        
        return create_response(200, {
            'success': True,
            'step_id': step_id,
            'status': status
        })
    
    except Exception as e:
        print(f'Error updating step status: {str(e)}')
        return create_response(500, {'error': 'Failed to update step status'})
