"""
Lambda function for updating execution status.

This endpoint allows CI/CD runners to update execution status as tests progress.

Endpoint: PATCH /api/usecases/{id}/executions/{execution_id}/status
"""
import json
import os
import boto3
from typing import Dict, Any
from datetime import datetime

from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    require_scopes
)
from test_suite_schema import (
    get_suite_execution_pk,
    get_execution_sk
)

dynamodb = boto3.client('dynamodb')
eventbridge = boto3.client('events')


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
        200: Status updated successfully
        400: Invalid status value
        403: Insufficient permissions
        404: Execution not found
        500: Internal server error
    """
    # Validate authentication and authorization
    user_identity, error_response = require_scopes(
        event,
        ['api/executions.write']
    )
    if error_response:
        return error_response
    
    print(f"Execution status update requested by: {user_identity['identity']} (type: {user_identity['identity_type']})")
    
    # Parse path parameters
    usecase_id = event.get('pathParameters', {}).get('id')
    execution_id = event.get('pathParameters', {}).get('executionId')
    
    if not usecase_id or not execution_id:
        return create_response(400, {'error': 'Missing usecase ID or execution ID'})
    
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
        
        # Publish EventBridge event for status change
        try:
            event_detail = {
                'usecase_id': usecase_id,
                'execution_id': execution_id,
                'status': status,
                'timestamp': get_current_timestamp()
            }
            
            if error_message:
                event_detail['error_message'] = error_message
            
            eventbridge.put_events(
                Entries=[{
                    'Source': 'nova-act-qa-studio.execution',
                    'DetailType': 'nova-act-qa-studio.execution.status-changed',
                    'Detail': json.dumps(event_detail),
                    'EventBusName': 'default'
                }]
            )
            print(f'Published execution status changed event')
        except Exception as e:
            print(f'Error publishing EventBridge event: {str(e)}')
            # Don't fail the request if event publishing fails
        
        # Update suite execution counters for terminal statuses
        item = get_response['Item']
        suite_execution_id = item.get('suite_execution_id', {}).get('S')
        suite_id = item.get('suite_id', {}).get('S')
        
        if status in ['success', 'failed'] and suite_execution_id and suite_id:
            try:
                if status == 'success':
                    counter_update_expr = 'ADD completed_usecases :inc, successful_usecases :inc, running_usecases :dec'
                else:
                    counter_update_expr = 'ADD completed_usecases :inc, failed_usecases :inc, running_usecases :dec'
                
                dynamodb.update_item(
                    TableName=table_name,
                    Key={
                        'pk': {'S': get_suite_execution_pk(suite_id)},
                        'sk': {'S': get_execution_sk(suite_execution_id)}
                    },
                    UpdateExpression=counter_update_expr,
                    ExpressionAttributeValues={
                        ':inc': {'N': '1'},
                        ':dec': {'N': '-1'}
                    }
                )
                print(f'Updated suite execution counters for suite_execution={suite_execution_id}, status={status}')
            except Exception as e:
                print(f'Error updating suite execution counters: {str(e)}')
                # Don't fail the request if suite counter update fails
        
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
