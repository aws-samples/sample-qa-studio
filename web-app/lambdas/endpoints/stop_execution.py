import lambda_init  # noqa: F401 — must be first import (running_executions uses pydantic from dependencies/)
import logging
from typing import Any, Dict
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from utils import create_response, get_table_name, get_current_timestamp, validate_path_id
from resource_auth import require_resource_access, execution_from_path
from running_executions import clear_running_execution
from execution_transitions import record_microvm_runtime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

TERMINAL_STATUSES = ('success', 'failed', 'stopped', 'error')


def mark_execution_stopped(table, dynamodb_client, table_name: str, usecase_id: str, execution_id: str) -> str:
    """Write ``status = stopped`` + ``completed_at`` on the execution record and
    drop its RUNNING_EXECUTIONS tracking record (best-effort); returns the timestamp."""
    completed_at = get_current_timestamp()
    table.update_item(
        Key={
            'pk': f'USECASE_EXECUTION#{usecase_id}',
            'sk': f'EXECUTION#{execution_id}'
        },
        UpdateExpression='SET #status = :status, completed_at = :completed_at',
        ExpressionAttributeNames={
            '#status': 'status'
        },
        ExpressionAttributeValues={
            ':status': 'stopped',
            ':completed_at': completed_at
        }
    )
    logger.info(f"Updated execution {execution_id} status to stopped")
    clear_running_execution(dynamodb_client, table_name, execution_id)
    return completed_at


def terminate_microvm(microvms, microvm_id: str) -> None:
    """Best-effort ``TerminateMicrovm``: idempotent server-side, so a VM that
    already exited (or is unknown) is logged, not raised."""
    logger.info(f"Terminating MicroVM: {microvm_id}")
    try:
        microvms.terminate_microvm(microvmIdentifier=microvm_id)
        logger.info(f"Successfully requested termination of MicroVM: {microvm_id}")
    except (ClientError, BotoCoreError) as e:
        logger.warning(f"Failed to terminate MicroVM {microvm_id}; execution is already marked stopped: {str(e)}")


@require_resource_access('execute', execution_from_path, scopes=['api/executions.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to stop a running execution.

    The execution record carries ``microvm_id`` (Lambda MicroVM runner). The
    record is marked ``stopped`` *before* ``TerminateMicrovm``: the platform's
    ``/terminate`` hook SIGTERMs the runner, whose final ``failed`` PATCH is
    then rejected by ``update_execution_status`` because the record is already
    terminal.  That rejection means the shared finalizer never runs for a
    stopped execution, so the VM's start/termination time is recorded here
    (``microvm_terminated_at`` = now; the VM is still winding down).
    A record without ``microvm_id`` is rejected with 400: executions
    of the removed ECS runtime (``task_arn``) are all terminal by now and can
    no longer be stopped.
    Requires api/executions.write scope.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with stop confirmation
    """
    try:
        # Get parameters from path
        execution_id, error = validate_path_id(event.get('pathParameters', {}).get('executionId'), 'execution ID')
        if error:
            return error
        usecase_id = event['pathParameters']['id']  # validated by the resolver
        
        # Initialize Amazon DynamoDB client
        table_name = get_table_name()
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        # Load execution to get its MicroVM identifier
        response = table.get_item(
            Key={
                'pk': f'USECASE_EXECUTION#{usecase_id}',
                'sk': f'EXECUTION#{execution_id}'
            }
        )
        
        if 'Item' not in response:
            return create_response(404, {'error': 'execution not found'})
        
        execution = response['Item']
        
        microvm_id = execution.get('microvm_id', '')
        if not microvm_id:
            return create_response(400, {'error': 'execution has no associated MicroVM'})
        
        # Check if execution is already in a terminal state
        status = execution.get('status', '')
        if status in TERMINAL_STATUSES:
            return create_response(400, {'error': f'execution is already in terminal state: {status}'})

        # stopped FIRST so the runner's SIGTERM handler finds a terminal record
        dynamodb_client = boto3.client('dynamodb')
        completed_at = mark_execution_stopped(table, dynamodb_client, table_name, usecase_id, execution_id)
        microvms = boto3.client('lambda-microvms')  # lazily: only once a VM is known
        terminate_microvm(microvms, microvm_id)
        record_microvm_runtime(dynamodb_client, microvms, table_name, usecase_id, execution_id, microvm_id)
        return create_response(200, {
            'status': 'stopped',
            'executionId': execution_id,
            'microvmId': microvm_id,
            'stoppedAt': completed_at
        })
        
    except Exception as e:
        logger.error(f"Error stopping execution: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
