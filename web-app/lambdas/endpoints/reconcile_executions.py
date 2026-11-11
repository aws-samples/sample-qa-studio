"""Scheduled reconciler for MicroVM executions whose VM died without reporting.

Runs every 5 minutes from an EventBridge schedule (no API Gateway).  It
*queries* the bounded ``RUNNING_EXECUTIONS`` partition (one tracking record
per in-flight VM, see :mod:`running_executions`), asks ``GetMicrovm`` about
each VM and marks the execution ``failed`` through the same terminal
transition the API uses (:mod:`execution_transitions`) when:

* the VM is ``TERMINATED`` or no longer exists (``ResourceNotFoundException``), or
* ``now`` is past the record's ``deadline`` (``started_at`` + the VM's maximum
  duration + :data:`running_executions.DEADLINE_GRACE`), whatever the VM state.

Before writing, the execution record is re-read: an already terminal record
(the runner / ``stop_execution`` got there first) or a missing one only loses
its tracking record — no status write, no event, no counters.

Expected steady state is zero reconciled executions; the
``ReconciledExecutions`` alarm in the worker stack treats any non-zero sum
as a supervisor/runner bug signal.  ``RunningMicrovms`` is published for
capacity visibility (the regional MicroVM memory quota).
"""
import lambda_init  # noqa: F401 — must be first import (running_executions uses pydantic from dependencies/)
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from execution_transitions import TERMINAL_STATUSES, execution_key, mark_execution_failed
from microvm_launch import get_microvm_client
from running_executions import RunningExecutionRecord, clear_running_execution, list_running_executions
from utils import get_table_name

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

METRIC_NAMESPACE = 'QAStudio/Worker'
METRIC_RUNNING = 'RunningMicrovms'
METRIC_RECONCILED = 'ReconciledExecutions'

#: VM states that count towards ``RunningMicrovms``.
LIVE_STATES = frozenset({'RUNNING', 'PENDING'})

dynamodb = boto3.client('dynamodb')
eventbridge = boto3.client('events')
cloudwatch = boto3.client('cloudwatch')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def decide(record: RunningExecutionRecord, microvm: Optional[Dict[str, Any]], now: datetime) -> Optional[str]:
    """Reason the execution must be failed, or ``None`` when it is healthy.

    ``microvm`` is the ``GetMicrovm`` response, or ``None`` when the VM no
    longer exists.  Order: dead VM first (its reason is more specific), then
    the deadline regardless of state.
    """
    if microvm is None:
        return 'microvm not found'
    state = microvm.get('state', 'UNKNOWN')
    if state == 'TERMINATED':
        return 'microvm TERMINATED'
    if now > record.deadline_at():
        return f'deadline exceeded (state={state})'
    return None


def _get_microvm(client, microvm_id: str) -> Optional[Dict[str, Any]]:
    """``GetMicrovm`` response, or ``None`` on ``ResourceNotFoundException``; other errors propagate."""
    try:
        return client.get_microvm(microvmIdentifier=microvm_id)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return None
        raise


def _reconcile_record(record: RunningExecutionRecord, table_name: str, now: datetime) -> Dict[str, int]:
    """One tracking record; returns the counters it contributes to the summary."""
    microvm = _get_microvm(get_microvm_client(), record.microvm_id)
    is_live = microvm is not None and microvm.get('state') in LIVE_STATES
    counters = {'reconciled': 0, 'cleared': 0, 'running': int(is_live)}

    reason = decide(record, microvm, now)
    if reason is None:
        return counters

    execution_id, usecase_id = record.execution_id, record.usecase_id
    response = dynamodb.get_item(TableName=table_name, Key=execution_key(usecase_id, execution_id))
    item = response.get('Item')
    if item is None:
        logger.warning('Execution %s (usecase %s) not found; dropping its tracking record (%s)',
                       execution_id, usecase_id, reason)
        counters['cleared'] = int(clear_running_execution(dynamodb, table_name, execution_id))
        return counters

    current_status = item.get('status', {}).get('S', '')
    if current_status in TERMINAL_STATUSES:
        logger.info('Execution %s already %s; dropping its stale tracking record (%s)',
                    execution_id, current_status, reason)
        counters['cleared'] = int(clear_running_execution(dynamodb, table_name, execution_id))
        return counters

    # Status write + event + cache wipe + suite counters + tracking-record
    # delete.  A failed status write propagates: the record stays for the next pass.
    mark_execution_failed(dynamodb, eventbridge, table_name, usecase_id, execution_id,
                          f'reconciler: {reason}', item)
    counters['reconciled'] = 1
    counters['cleared'] = 1
    return counters


def _publish_metrics(running: int, reconciled: int, now: datetime) -> None:
    """Both counts in one call; zeros too, so the alarm never sees missing data. Best-effort."""
    try:
        cloudwatch.put_metric_data(
            Namespace=METRIC_NAMESPACE,
            MetricData=[
                {'MetricName': METRIC_RUNNING, 'Value': running, 'Unit': 'Count', 'Timestamp': now},
                {'MetricName': METRIC_RECONCILED, 'Value': reconciled, 'Unit': 'Count', 'Timestamp': now},
            ],
        )
    except Exception as e:  # noqa: BLE001 — metrics must not fail the sweep
        logger.error('Failed to publish %s metrics: %s', METRIC_NAMESPACE, e)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, int]:
    """EventBridge schedule entry point. Returns ``{checked, reconciled, cleared, running}``."""
    table_name = get_table_name()
    now = _now()
    records = list_running_executions(dynamodb, table_name)

    summary = {'checked': len(records), 'reconciled': 0, 'cleared': 0, 'running': 0}
    for record in records:
        try:
            for key, value in _reconcile_record(record, table_name, now).items():
                summary[key] += value
        except Exception as e:  # noqa: BLE001 — one record must not stop the sweep
            logger.error('Reconciling execution %s (microvm %s) failed: %s',
                         record.execution_id, record.microvm_id, e, exc_info=True)

    _publish_metrics(summary['running'], summary['reconciled'], now)
    logger.info(json.dumps({'event': 'reconcile_executions', **summary}))
    return summary
