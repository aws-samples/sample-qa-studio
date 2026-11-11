"""The one implementation of a use-case execution's terminal transition.

Two callers report a finished execution:

* ``update_execution_status`` — the API path (runner / CI PATCH).
* ``reconcile_executions`` — the scheduled Lambda that finds executions whose
  MicroVM died without reporting.

Both must leave the same trail: the MicroVM start/termination timestamps on
the execution record, the EventBridge
``nova-act-qa-studio.execution.status.changed`` event, the cache wipe on
``failed``, the suite-execution counters, suite completion + test-suite
summary, and the ``RUNNING_EXECUTIONS`` tracking-record delete.  Everything
after the execution's own status write lives here so it cannot drift.

``stop_execution`` and ``terminate_wizard_session`` write their own terminal
status and do not run the finalizer (the runner's late PATCH is rejected, so
nothing else would record the VM); they call
:func:`record_microvm_runtime` directly.

Every side effect is best-effort: the status write has already happened by the
time :func:`finalize_terminal_transition` runs, and none of the follow-ups may
turn a recorded transition into a failed request.  Each is logged on error and
the next one still runs.
"""
import lambda_init  # noqa: F401 — must be first import (running_executions uses pydantic from dependencies/)
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from cache_invalidation import cleanup_cache_artifacts
from microvm_launch import get_microvm_client
from running_executions import clear_running_execution
from test_suite_schema import get_execution_sk, get_suite_execution_pk
from utils import get_current_timestamp

logger = logging.getLogger(__name__)

#: Statuses no later write may overwrite. ``stop_execution`` writes ``stopped``
#: before terminating the worker, so the runner's late ``failed`` lands here.
#: ``timeout`` is written by the wizard worker's inactivity path (the VM then
#: self-terminates); without it the reconciler would mark every timed-out
#: wizard session ``failed`` and fire the ``ReconciledExecutions`` alarm.
TERMINAL_STATUSES = frozenset({'success', 'failed', 'stopped', 'error', 'completed', 'timeout'})

#: Only these two move the suite-execution counters (``stopped`` / ``error`` /
#: ``completed`` / ``timeout`` never did on the API path; kept identical).
_COUNTED_STATUSES = frozenset({'success', 'failed'})

EVENT_SOURCE = 'nova-act-qa-studio.execution'
EVENT_DETAIL_TYPE = 'nova-act-qa-studio.execution.status.changed'


def execution_key(usecase_id: str, execution_id: str) -> Dict[str, Dict[str, str]]:
    """Typed DynamoDB key of the execution record."""
    return {
        'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
        'sk': {'S': f'EXECUTION#{execution_id}'},
    }


def _rfc3339(value: datetime) -> str:
    """Same ``YYYY-MM-DDTHH:MM:SSZ`` shape as every other timestamp on the record."""
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def record_microvm_runtime(
    dynamodb,
    microvms,
    table_name: str,
    usecase_id: str,
    execution_id: str,
    microvm_id: str,
) -> bool:
    """Persist the VM's lifetime on the execution record for the daily cost allocation.

    One ``GetMicrovm`` call; writes ``microvm_started_at`` (``startedAt``) and
    ``microvm_terminated_at`` (``terminatedAt``, or *now* while the VM has not
    reached ``TERMINATED`` yet — right after ``stop_execution`` / the wizard
    terminate the VM is still winding down).  Both attributes or neither: a
    VM without ``startedAt`` never ran.

    Best-effort like every follow-up here: a VM that is already gone
    (``ResourceNotFoundException``), any other ``ClientError`` /
    ``BotoCoreError`` and a failed write are logged at WARNING and the
    transition goes on.  Returns ``True`` when both fields were written.
    Executions that finish without this write are allocated by wall-clock.
    """
    try:
        microvm = microvms.get_microvm(microvmIdentifier=microvm_id)
    except (ClientError, BotoCoreError) as e:
        logger.warning('GetMicrovm %s for execution %s failed; no VM runtime recorded: %s',
                       microvm_id, execution_id, e)
        return False

    started_at = microvm.get('startedAt')
    if started_at is None:
        logger.warning('MicroVM %s for execution %s has no startedAt (state=%s); no VM runtime recorded',
                       microvm_id, execution_id, microvm.get('state', 'UNKNOWN'))
        return False
    terminated_at = microvm.get('terminatedAt')
    terminated_value = _rfc3339(terminated_at) if terminated_at is not None else get_current_timestamp()

    try:
        dynamodb.update_item(
            TableName=table_name,
            Key=execution_key(usecase_id, execution_id),
            UpdateExpression='SET microvm_started_at = :started_at, microvm_terminated_at = :terminated_at',
            ExpressionAttributeValues={
                ':started_at': {'S': _rfc3339(started_at)},
                ':terminated_at': {'S': terminated_value},
            },
        )
    except (ClientError, BotoCoreError) as e:
        logger.warning('Failed to record MicroVM %s runtime on execution %s: %s', microvm_id, execution_id, e)
        return False
    logger.info('Recorded MicroVM %s runtime on execution %s', microvm_id, execution_id)
    return True


def mark_execution_failed(
    dynamodb,
    eventbridge,
    table_name: str,
    usecase_id: str,
    execution_id: str,
    error_message: str,
    execution_item: Dict[str, Any],
) -> None:
    """Write ``status=failed`` (+ ``completed_at``, ``error_message``) and run the follow-ups.

    Same ``UpdateExpression`` shape the API handler builds for a ``failed``
    PATCH carrying an ``error_message``.  The status write propagates its
    error (nothing else runs then); the follow-ups are best-effort.
    ``execution_item`` is the record as read *before* this write (typed
    low-level shape) — only ``suite_execution_id`` / ``suite_id`` are used.
    """
    now = get_current_timestamp()
    dynamodb.update_item(
        TableName=table_name,
        Key=execution_key(usecase_id, execution_id),
        UpdateExpression=(
            'SET #status = :status, updated_at = :updated_at, completed_at = :completed_at, '
            'error_message = :error_message'
        ),
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={
            ':status': {'S': 'failed'},
            ':updated_at': {'S': now},
            ':completed_at': {'S': now},
            ':error_message': {'S': error_message},
        },
    )
    logger.info('Marked execution %s (usecase %s) failed: %s', execution_id, usecase_id, error_message)
    finalize_terminal_transition(
        dynamodb, eventbridge, table_name, usecase_id, execution_id, 'failed', execution_item,
        error_message=error_message,
    )


def finalize_terminal_transition(
    dynamodb,
    eventbridge,
    table_name: str,
    usecase_id: str,
    execution_id: str,
    status: str,
    execution_item: Dict[str, Any],
    *,
    error_message: Optional[str] = None,
) -> None:
    """Everything that follows an execution's terminal status write, in this order:

    1. record the MicroVM's start/termination time (``GetMicrovm``; items
       without ``microvm_id`` — ``ci_runner``, pre-MicroVM records — skip it),
    2. delete the ``RUNNING_EXECUTIONS`` tracking record,
    3. publish the status-changed EventBridge event,
    4. on ``failed``: wipe the use case's cache/trajectory artifacts,
    5. on ``success`` / ``failed`` with suite membership: bump the suite
       counters, finalize the suite execution when the last use case lands,
       and update the test-suite summary.

    ``status`` must be one of :data:`TERMINAL_STATUSES`.  Never raises.
    """
    if status not in TERMINAL_STATUSES:
        raise ValueError(f'{status!r} is not a terminal status')

    # First, while the VM is still readable: the cost allocation needs its
    # exact lifetime and terminated VMs age out of GetMicrovm.
    microvm_id = execution_item.get('microvm_id', {}).get('S', '')
    if microvm_id:
        record_microvm_runtime(dynamodb, get_microvm_client(), table_name, usecase_id, execution_id, microvm_id)

    # A finished execution leaves the RUNNING_EXECUTIONS partition the
    # reconciler queries (best-effort; the helper logs and never raises).
    clear_running_execution(dynamodb, table_name, execution_id)

    publish_status_changed(eventbridge, usecase_id, execution_id, status, error_message)

    # Option C cache invalidation: when an execution transitions to ``failed``,
    # wipe all cache/trajectory pointers + S3 blobs for the usecase so the
    # NEXT execution starts from a clean slate. Coarse (clears even steps that
    # weren't involved in the failure) but reliable — the alternative per-step
    # cleanup paths have gaps, see the RCA for Option C. Best effort.
    if status == 'failed':
        _cleanup_usecase_cache(table_name, usecase_id, execution_id)

    suite_execution_id = execution_item.get('suite_execution_id', {}).get('S')
    suite_id = execution_item.get('suite_id', {}).get('S')
    if status in _COUNTED_STATUSES and suite_execution_id and suite_id:
        _update_suite_execution(dynamodb, table_name, suite_id, suite_execution_id, status)


def publish_status_changed(eventbridge, usecase_id: str, execution_id: str, status: str,
                           error_message: Optional[str] = None) -> None:
    """Publish ``nova-act-qa-studio.execution.status.changed`` on the default bus (best-effort).

    Public because the API handler also publishes it for the non-terminal
    ``pending`` / ``running`` writes, which have no other follow-ups.
    """
    try:
        event_detail = {
            'usecase_id': usecase_id,
            'execution_id': execution_id,
            'status': status,
            'timestamp': get_current_timestamp(),
        }
        if error_message:
            event_detail['error_message'] = error_message
        eventbridge.put_events(
            Entries=[{
                'Source': EVENT_SOURCE,
                'DetailType': EVENT_DETAIL_TYPE,
                'Detail': json.dumps(event_detail),
                'EventBusName': 'default',
            }]
        )
        print('Published execution status changed event')
    except Exception as e:  # noqa: BLE001 — best-effort, the transition is already recorded
        print(f'Error publishing Amazon EventBridge event: {str(e)}')


def _cleanup_usecase_cache(table_name: str, usecase_id: str, execution_id: str) -> None:
    try:
        s3_bucket = os.environ.get('S3_BUCKET', '')
        # cleanup_cache_artifacts expects a resource-style Table handle; the
        # callers hold the low-level client, so build a resource just for it.
        table = boto3.resource('dynamodb').Table(table_name)
        cleanup_cache_artifacts(table, usecase_id, s3_bucket)
        print(f'Cleared cache artifacts for usecase {usecase_id} after failed execution {execution_id}')
    except Exception as cleanup_exc:  # noqa: BLE001 — best-effort
        print(f'Cache cleanup after failed execution {execution_id}: {cleanup_exc}')


def _update_suite_execution(dynamodb, table_name: str, suite_id: str, suite_execution_id: str,
                            status: str) -> None:
    """Counters, then (when every use case landed) suite status + test-suite summary."""
    try:
        if status == 'success':
            counter_update_expr = 'ADD completed_usecases :inc, successful_usecases :inc, running_usecases :dec'
        else:
            counter_update_expr = 'ADD completed_usecases :inc, failed_usecases :inc, running_usecases :dec'

        suite_key = {
            'pk': {'S': get_suite_execution_pk(suite_id)},
            'sk': {'S': get_execution_sk(suite_execution_id)},
        }
        update_response = dynamodb.update_item(
            TableName=table_name,
            Key=suite_key,
            UpdateExpression=counter_update_expr,
            ExpressionAttributeValues={':inc': {'N': '1'}, ':dec': {'N': '-1'}},
            ReturnValues='ALL_NEW',
        )
        print(f'Updated suite execution counters for suite_execution={suite_execution_id}, status={status}')

        suite_exec = update_response.get('Attributes', {})
        total = int(suite_exec.get('total_usecases', {}).get('N', '0'))
        completed = int(suite_exec.get('completed_usecases', {}).get('N', '0'))
        if not (total > 0 and completed >= total):
            return

        failed_count = int(suite_exec.get('failed_usecases', {}).get('N', '0'))
        final_status = 'failed' if failed_count > 0 else 'completed'
        completed_at = get_current_timestamp()

        duration_ms = 0
        started_at = suite_exec.get('started_at', {}).get('S', '')
        if started_at:
            try:
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
                ':duration': {'N': str(duration_ms)},
            },
        )
        print(f'Suite execution {suite_execution_id} finalized as {final_status} (duration: {duration_ms}ms)')

        successful_count = int(suite_exec.get('successful_usecases', {}).get('N', '0'))
        dynamodb.update_item(
            TableName=table_name,
            Key={'pk': {'S': 'TEST_SUITES'}, 'sk': {'S': f'SUITE#{suite_id}'}},
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
            },
        )
        print(f'Updated test suite {suite_id} summary')
    except Exception as e:  # noqa: BLE001 — best-effort
        print(f'Error updating suite execution counters: {str(e)}')
