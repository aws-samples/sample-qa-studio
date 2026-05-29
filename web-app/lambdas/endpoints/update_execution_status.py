"""
AWS Lambda function for updating execution status.

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
    require_scopes,
    validate_path_id)
from test_suite_schema import (
    get_suite_execution_pk,
    get_execution_sk
)
from cache_invalidation import cleanup_cache_artifacts

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
        
        # Publish Amazon EventBridge event for status change
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
                    'DetailType': 'nova-act-qa-studio.execution.status.changed',
                    'Detail': json.dumps(event_detail),
                    'EventBusName': 'default'
                }]
            )
            print(f'Published execution status changed event')
        except Exception as e:
            print(f'Error publishing Amazon EventBridge event: {str(e)}')
            # Don't fail the request if event publishing fails

        # Option C cache invalidation: when an execution transitions
        # to ``failed``, wipe all cache/trajectory pointers + S3 blobs
        # for the usecase so the NEXT execution starts from a clean
        # slate. Coarse (clears even steps that weren't involved in
        # the failure) but reliable — the alternative per-step
        # cleanup paths have gaps, see the RCA for Option C. Best
        # effort; any error is logged and we continue.
        if status == 'failed':
            try:
                s3_bucket = os.environ.get('S3_BUCKET', '')
                # cleanup_cache_artifacts expects a resource-style
                # Table handle; this Lambda otherwise uses the
                # low-level client for efficiency, so we build a
                # resource here just for the helper.
                dynamodb_resource = boto3.resource('dynamodb')
                table = dynamodb_resource.Table(table_name)
                cleanup_cache_artifacts(table, usecase_id, s3_bucket)
                print(
                    f'Cleared cache artifacts for usecase {usecase_id} '
                    f'after failed execution {execution_id}'
                )
            except Exception as cleanup_exc:  # noqa: BLE001 — best-effort
                print(
                    f'Cache cleanup after failed execution {execution_id}: '
                    f'{cleanup_exc}'
                )

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
                
                suite_key = {
                    'pk': {'S': get_suite_execution_pk(suite_id)},
                    'sk': {'S': get_execution_sk(suite_execution_id)}
                }
                update_response = dynamodb.update_item(
                    TableName=table_name,
                    Key=suite_key,
                    UpdateExpression=counter_update_expr,
                    ExpressionAttributeValues={
                        ':inc': {'N': '1'},
                        ':dec': {'N': '-1'}
                    },
                    ReturnValues='ALL_NEW'
                )
                print(f'Updated suite execution counters for suite_execution={suite_execution_id}, status={status}')

                # Check if all usecases completed — if so, finalize suite execution status
                suite_exec = update_response.get('Attributes', {})
                total = int(suite_exec.get('total_usecases', {}).get('N', '0'))
                completed = int(suite_exec.get('completed_usecases', {}).get('N', '0'))

                if total > 0 and completed >= total:
                    failed_count = int(suite_exec.get('failed_usecases', {}).get('N', '0'))
                    final_status = 'failed' if failed_count > 0 else 'completed'
                    completed_at = get_current_timestamp()

                    # Compute duration from started_at to now
                    duration_ms = 0
                    started_at = suite_exec.get('started_at', {}).get('S', '')
                    if started_at:
                        try:
                            from datetime import datetime, timezone
                            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                            end = datetime.now(timezone.utc)
                            duration_ms = int((end - start).total_seconds() * 1000)
                        except (ValueError, TypeError):
                            pass

                    dynamodb.update_item(
                        TableName=table_name,
                        Key=suite_key,
                        UpdateExpression='SET #status = :status, completed_at = :completed_at, duration_ms = :duration',
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={
                            ':status': {'S': final_status},
                            ':completed_at': {'S': completed_at},
                            ':duration': {'N': str(duration_ms)}
                        }
                    )
                    print(f'Suite execution {suite_execution_id} finalized as {final_status} (duration: {duration_ms}ms)')

                    # Propagate to test suite summary record
                    successful_count = int(suite_exec.get('successful_usecases', {}).get('N', '0'))
                    dynamodb.update_item(
                        TableName=table_name,
                        Key={
                            'pk': {'S': 'TEST_SUITES'},
                            'sk': {'S': f'SUITE#{suite_id}'}
                        },
                        UpdateExpression=(
                            'SET last_execution_status = :status, '
                            'last_execution_time = :time, '
                            'last_execution_id = :exec_id, '
                            'last_successful_count = :successful, '
                            'last_failed_count = :failed'
                        ),
                        ExpressionAttributeValues={
                            ':status': {'S': final_status},
                            ':time': {'S': completed_at},
                            ':exec_id': {'S': suite_execution_id},
                            ':successful': {'N': str(successful_count)},
                            ':failed': {'N': str(failed_count)},
                        }
                    )
                    print(f'Updated test suite {suite_id} summary')
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
