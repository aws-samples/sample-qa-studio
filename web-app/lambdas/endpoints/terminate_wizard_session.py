import lambda_init  # noqa: F401 — must be first import (running_executions uses pydantic from dependencies/)
import json
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from execution_transitions import record_microvm_runtime
from resource_auth import require_resource_access, wizard_session_from_path
from running_executions import clear_running_execution
from utils import create_response, get_table_name, get_current_timestamp, validate_path_id

dynamodb = boto3.client('dynamodb')
sqs = boto3.client('sqs')
eventbridge = boto3.client('events')


def execution_key(usecase_id: str, session_id: str) -> dict:
    return {
        'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
        'sk': {'S': f'EXECUTION#{session_id}'}
    }


def session_microvm_id(table_name: str, usecase_id: str, session_id: str) -> str:
    """``microvm_id`` of the session's execution record; '' when the session
    runs elsewhere (started before the MicroVM switch) or the read fails."""
    try:
        response = dynamodb.get_item(TableName=table_name, Key=execution_key(usecase_id, session_id))
    except (ClientError, BotoCoreError) as e:
        print(f'Error reading execution record for session {session_id}: {str(e)}')
        return ''
    return response.get('Item', {}).get('microvm_id', {}).get('S', '')


def mark_session_closed(table_name: str, usecase_id: str, session_id: str) -> None:
    """Make the session's execution record terminal before the VM is terminated.

    ``status = success`` + ``wizard_status = closed`` + ``completed_at`` in one
    conditional write (only while ``pending`` / ``running``).  When the record
    is already terminal (``failed``, ``timeout``, ``success``) the condition
    fails and only ``wizard_status`` / ``completed_at`` are written — the
    terminal status is kept.  Any other error is logged; the termination goes
    on regardless (the command and ``TerminateMicrovm`` end the session).
    """
    key = execution_key(usecase_id, session_id)
    now = get_current_timestamp()
    try:
        dynamodb.update_item(
            TableName=table_name,
            Key=key,
            UpdateExpression='SET #status = :success, wizard_status = :closed, completed_at = :now',
            ConditionExpression='#status IN (:pending, :running)',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':success': {'S': 'success'},
                ':closed': {'S': 'closed'},
                ':now': {'S': now},
                ':pending': {'S': 'pending'},
                ':running': {'S': 'running'},
            },
        )
        print(f'Marked wizard session {session_id} success/closed')
        return
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') != 'ConditionalCheckFailedException':
            print(f'Error updating execution status for session {session_id}: {str(e)}')
            return
        print(f'Wizard session {session_id} is already terminal; closing without a status change')
    except Exception as e:  # noqa: BLE001 — best-effort, termination continues
        print(f'Error updating execution status for session {session_id}: {str(e)}')
        return

    try:
        dynamodb.update_item(
            TableName=table_name,
            Key=key,
            UpdateExpression='SET wizard_status = :status, completed_at = :completed',
            ExpressionAttributeValues={
                ':status': {'S': 'closed'},
                ':completed': {'S': now},
            },
        )
        print(f'Updated wizard_status to closed for session {session_id}')
    except Exception as e:  # noqa: BLE001 — best-effort, termination continues
        print(f'Error updating execution status for session {session_id}: {str(e)}')


def terminate_microvm(microvms, microvm_id: str) -> None:
    """Best-effort ``TerminateMicrovm``: idempotent server-side, so a VM that
    already exited (the worker handled the command first and the supervisor
    self-terminated) is logged, not raised."""
    print(f'Terminating MicroVM {microvm_id}')
    try:
        microvms.terminate_microvm(microvmIdentifier=microvm_id)
        print(f'Requested termination of MicroVM {microvm_id}')
    except (ClientError, BotoCoreError) as e:
        print(f'Failed to terminate MicroVM {microvm_id}; the terminate command was sent: {str(e)}')


@require_resource_access('edit', wizard_session_from_path, scopes=['api/usecases.write'])
def handler(event, context):
    """
    Terminate a wizard session: make the execution record terminal, send the
    terminate command to the wizard worker, then terminate the session's
    MicroVM (when the execution record carries ``microvm_id``), record the
    VM's start/termination time on the execution record and drop its
    RUNNING_EXECUTIONS tracking record.

    The status is written *first*, like ``stop_execution`` does: ``TerminateMicrovm``
    makes the platform's ``/terminate`` hook SIGTERM ``wizard_worker.py`` within
    seconds, usually before the worker polls the command, so the worker may never
    write the ``success`` it wrote on a terminate command in the ECS era. Writing
    ``success`` here keeps that outcome; the worker's SIGTERM handler only cleans
    up the browser and never writes ``failed``.  Because the record is terminal
    before anything else reports, the shared finalizer never runs for a wizard
    session; the VM runtime is recorded here (``microvm_terminated_at`` = now
    while the VM winds down, the VM's own ``terminatedAt`` when the worker
    already ended it).
    
    Path Parameters:
    - sessionId: The wizard session ID to terminate
    - usecaseId: The usecase ID associated with the session
    
    Returns:
    - 200: Session terminated successfully (``microvmId`` when a VM was terminated)
    - 400: Missing required parameters
    - 403: Insufficient scopes or no edit access to the use case
    - 404: Session not found under the use case
    - 500: Error terminating session
    """
    session_id, error = validate_path_id(event.get('pathParameters', {}).get('sessionId'), 'session ID')
    if error:
        return error
    usecase_id, error = validate_path_id(event.get('pathParameters', {}).get('usecaseId'), 'usecase ID')
    if error:
        return error
    
    table_name = get_table_name()
    mark_session_closed(table_name, usecase_id, session_id)
    
    # Send terminate command for graceful shutdown
    command = {
        'action': 'terminate',
        'sessionId': session_id
    }
    
    event_bus_name = os.environ.get('WIZARD_EVENT_BUS_NAME')
    
    try:
        if event_bus_name:
            # Send to Amazon EventBridge (new approach)
            eventbridge.put_events(
                Entries=[{
                    'Source': 'wizard.commands',
                    'DetailType': 'WizardCommand',
                    'Detail': json.dumps(command),
                    'EventBusName': event_bus_name
                }]
            )
            print(f'Terminate command sent to Amazon EventBridge for session {session_id}')
        else:
            # Fallback to Amazon SQS (legacy approach)
            queue_url = os.environ['WIZARD_QUEUE_URL']
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(command)
            )
            print(f'Terminate command sent to SQS for session {session_id}')
    except Exception as e:
        print(f'Error sending terminate command: {str(e)}')
        return create_response(500, {'error': 'Failed to send terminate command'})

    # The VM the session runs on: terminate it, record its lifetime for the
    # cost allocation and leave the RUNNING_EXECUTIONS partition the reconciler
    # queries. All three are best-effort — the record is already terminal
    # (above); the VM also self-terminates when the worker exits, and the
    # reconciler cleans up a VM that outlived both.
    microvm_id = session_microvm_id(table_name, usecase_id, session_id)
    if not microvm_id:
        return create_response(200, {'status': 'terminated'})

    microvms = boto3.client('lambda-microvms')  # lazily: sessions without a VM never need it
    terminate_microvm(microvms, microvm_id)
    record_microvm_runtime(dynamodb, microvms, table_name, usecase_id, session_id, microvm_id)
    clear_running_execution(dynamodb, table_name, session_id)
    return create_response(200, {'status': 'terminated', 'microvmId': microvm_id})
