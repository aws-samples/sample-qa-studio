"""
Lambda function for updating suite execution status.

This endpoint allows CI/CD runners to update suite execution status
after all use cases have completed.

Endpoint: PATCH /api/test-suites/{suite_id}/executions/{execution_id}/status
"""
import json
import boto3
from typing import Dict, Any

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


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Update suite execution status.

    Path Parameters:
        suite_id: Test suite UUID
        execution_id: Suite execution UUID

    Request Body:
        status: New status (running, completed, partial, failed)

    Returns:
        200: Status updated successfully
        400: Invalid status value
        403: Insufficient permissions
        404: Suite execution not found
        500: Internal server error
    """
    # Validate authentication and authorization
    user_identity, error_response = require_scopes(
        event,
        ['api/executions.write']
    )
    if error_response:
        return error_response

    print(f"Suite execution status update requested by: {user_identity['identity']} (type: {user_identity['identity_type']})")

    # Parse path parameters
    suite_id = event.get('pathParameters', {}).get('suite_id')
    execution_id = event.get('pathParameters', {}).get('execution_id')

    if not suite_id or not execution_id:
        return create_response(400, {'error': 'Missing suite ID or execution ID'})

    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    # Validate status
    status = body.get('status')
    valid_statuses = ['running', 'completed', 'partial', 'failed']

    if not status:
        return create_response(400, {'error': 'Missing status field'})

    if status not in valid_statuses:
        return create_response(400, {
            'error': 'Invalid status',
            'message': f'Status must be one of: {", ".join(valid_statuses)}'
        })

    print(f'Updating suite execution {execution_id} status to: {status}')

    table_name = get_table_name()

    try:
        # Check if suite execution exists
        pk = get_suite_execution_pk(suite_id)
        sk = get_execution_sk(execution_id)

        get_response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': pk},
                'sk': {'S': sk}
            }
        )

        if 'Item' not in get_response:
            return create_response(404, {
                'error': 'Suite execution not found',
                'message': f'No suite execution found with ID: {execution_id}'
            })

        # Build update expression
        update_expr = 'SET #status = :status, updated_at = :updated_at'
        expr_attr_names = {'#status': 'status'}
        expr_attr_values = {
            ':status': {'S': status},
            ':updated_at': {'S': get_current_timestamp()}
        }

        # Add completed_at timestamp for terminal statuses
        if status in ['completed', 'partial', 'failed']:
            update_expr += ', completed_at = :completed_at'
            expr_attr_values[':completed_at'] = {'S': get_current_timestamp()}

            # Calculate duration if started_at exists
            item = get_response['Item']
            started_at = item.get('started_at', {}).get('S')
            if started_at:
                try:
                    from datetime import datetime
                    start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    end = datetime.fromisoformat(get_current_timestamp().replace('Z', '+00:00'))
                    duration_seconds = int((end - start).total_seconds())
                    update_expr += ', duration_seconds = :duration'
                    expr_attr_values[':duration'] = {'N': str(duration_seconds)}
                except Exception as e:
                    print(f'Could not calculate duration: {str(e)}')

        # Update suite execution status
        dynamodb.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': pk},
                'sk': {'S': sk}
            },
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )

        print(f'Updated suite execution {execution_id} to status: {status}')

        # Propagate results to test suite summary record for terminal statuses
        if status in ['completed', 'partial', 'failed']:
            try:
                item = get_response['Item']
                record_suite_id = item.get('suite_id', {}).get('S', suite_id)
                successful_usecases = int(item.get('successful_usecases', {}).get('N', '0'))
                failed_usecases = int(item.get('failed_usecases', {}).get('N', '0'))

                dynamodb.update_item(
                    TableName=table_name,
                    Key={
                        'pk': {'S': 'TEST_SUITES'},
                        'sk': {'S': f'SUITE#{record_suite_id}'}
                    },
                    UpdateExpression=(
                        'SET last_execution_status = :status, '
                        'last_execution_time = :time, '
                        'last_execution_id = :exec_id, '
                        'last_successful_count = :successful, '
                        'last_failed_count = :failed'
                    ),
                    ExpressionAttributeValues={
                        ':status': {'S': status},
                        ':time': {'S': get_current_timestamp()},
                        ':exec_id': {'S': execution_id},
                        ':successful': {'N': str(successful_usecases)},
                        ':failed': {'N': str(failed_usecases)},
                    }
                )
                print(f'Updated test suite {record_suite_id} summary with execution {execution_id} results')
            except Exception as e:
                print(f'Error updating test suite summary: {str(e)}')

        return create_response(200, {
            'suite_execution_id': execution_id,
            'status': status,
            'updated_at': get_current_timestamp()
        })

    except Exception as e:
        print(f'Error updating suite execution status: {str(e)}')
        import traceback
        traceback.print_exc()
        return create_response(500, {
            'error': 'Failed to update suite execution status',
            'message': str(e)
        })
