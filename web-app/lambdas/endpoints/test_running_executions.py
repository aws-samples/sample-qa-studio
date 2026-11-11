"""RUNNING_EXECUTIONS / EXECUTION#{execution_id} tracking record.

Written when a MicroVM is launched, deleted on every terminal transition, so
the reconciler can *query* in-flight executions instead of scanning the table.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from running_executions import (
    DEADLINE_GRACE,
    RUNNING_EXECUTIONS_PK,
    RunningExecutionRecord,
    clear_running_execution,
    list_running_executions,
    new_running_execution,
    put_running_execution,
    running_execution_key,
)

TABLE = 'test-table'
STARTED = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)


def _client_error(code='ProvisionedThroughputExceededException', operation='DeleteItem'):
    return ClientError({'Error': {'Code': code, 'Message': code}}, operation)


# ---------------------------------------------------------------------------
# Keys and model
# ---------------------------------------------------------------------------

def test_key_builders():
    assert RUNNING_EXECUTIONS_PK == 'RUNNING_EXECUTIONS'
    assert running_execution_key('exec-1') == {'pk': 'RUNNING_EXECUTIONS', 'sk': 'EXECUTION#exec-1'}


def test_new_record_fields_and_deadline_math():
    record = new_running_execution(
        execution_id='exec-1', usecase_id='uc-1', microvm_id='vm-1', mode='batch',
        max_duration_s=45 * 60, started_at=STARTED,
    )

    assert record.pk == 'RUNNING_EXECUTIONS'
    assert record.sk == 'EXECUTION#exec-1'
    assert record.execution_id == 'exec-1'
    assert record.usecase_id == 'uc-1'
    assert record.microvm_id == 'vm-1'
    assert record.mode == 'batch'
    assert record.suite_execution_id is None
    assert record.started_at == '2026-05-04T12:00:00Z'
    assert DEADLINE_GRACE == timedelta(minutes=10)
    # deadline = started_at + max duration + 10 min grace
    assert record.deadline == '2026-05-04T12:55:00Z'
    assert record.deadline_at() - record.started_at_dt() == timedelta(seconds=45 * 60) + DEADLINE_GRACE


def test_new_record_defaults_started_at_to_now():
    before = datetime.now(timezone.utc).replace(microsecond=0)
    record = new_running_execution(
        execution_id='exec-1', usecase_id='uc-1', microvm_id='vm-1', mode='wizard', max_duration_s=60,
        suite_execution_id='se-1',
    )
    after = datetime.now(timezone.utc)
    assert before <= record.started_at_dt() <= after
    assert record.mode == 'wizard'
    assert record.suite_execution_id == 'se-1'


@pytest.mark.parametrize('bad', [
    {'mode': 'ecs'},
    {'sk': 'STEP#exec-1'},
    {'pk': 'EXECUTIONS'},
    {'started_at': 'yesterday'},
])
def test_model_rejects_invalid_values(bad):
    fields = {
        'pk': 'RUNNING_EXECUTIONS', 'sk': 'EXECUTION#exec-1', 'usecase_id': 'uc-1', 'microvm_id': 'vm-1',
        'mode': 'batch', 'started_at': '2026-05-04T12:00:00Z', 'deadline': '2026-05-04T13:10:00Z',
    }
    fields.update(bad)
    with pytest.raises(ValidationError):
        RunningExecutionRecord(**fields)


def test_model_ignores_unknown_attributes_on_read():
    """A newer writer may add attributes; the reconciler must still parse the item."""
    record = RunningExecutionRecord(
        pk='RUNNING_EXECUTIONS', sk='EXECUTION#exec-1', usecase_id='uc-1', microvm_id='vm-1', mode='batch',
        started_at='2026-05-04T12:00:00Z', deadline='2026-05-04T13:10:00Z', future_attr='x',
    )
    assert record.execution_id == 'exec-1'


# ---------------------------------------------------------------------------
# put / clear / list against a low-level client
# ---------------------------------------------------------------------------

def test_put_writes_typed_item_without_null_optionals():
    client = MagicMock()
    record = new_running_execution(
        execution_id='exec-1', usecase_id='uc-1', microvm_id='vm-1', mode='batch',
        max_duration_s=600, started_at=STARTED,
    )

    put_running_execution(client, TABLE, record)

    client.put_item.assert_called_once_with(TableName=TABLE, Item={
        'pk': {'S': 'RUNNING_EXECUTIONS'},
        'sk': {'S': 'EXECUTION#exec-1'},
        'usecase_id': {'S': 'uc-1'},
        'microvm_id': {'S': 'vm-1'},
        'mode': {'S': 'batch'},
        'started_at': {'S': '2026-05-04T12:00:00Z'},
        'deadline': {'S': '2026-05-04T12:20:00Z'},
    })


def test_put_includes_suite_execution_id_when_present():
    client = MagicMock()
    record = new_running_execution(
        execution_id='exec-1', usecase_id='uc-1', microvm_id='vm-1', mode='batch',
        max_duration_s=600, started_at=STARTED, suite_execution_id='se-1',
    )
    put_running_execution(client, TABLE, record)
    assert client.put_item.call_args.kwargs['Item']['suite_execution_id'] == {'S': 'se-1'}


def test_put_propagates_errors_to_the_caller():
    client = MagicMock()
    client.put_item.side_effect = _client_error(operation='PutItem')
    record = new_running_execution(
        execution_id='exec-1', usecase_id='uc-1', microvm_id='vm-1', mode='batch', max_duration_s=600)
    with pytest.raises(ClientError):
        put_running_execution(client, TABLE, record)


def test_clear_deletes_the_item():
    client = MagicMock()
    assert clear_running_execution(client, TABLE, 'exec-1') is True
    client.delete_item.assert_called_once_with(
        TableName=TABLE, Key={'pk': {'S': 'RUNNING_EXECUTIONS'}, 'sk': {'S': 'EXECUTION#exec-1'}})


def test_clear_is_idempotent_on_a_missing_item():
    """DynamoDB DeleteItem on a missing key succeeds; a second clear is a no-op too."""
    client = MagicMock()
    client.delete_item.return_value = {}
    assert clear_running_execution(client, TABLE, 'exec-1') is True
    assert clear_running_execution(client, TABLE, 'exec-1') is True
    assert client.delete_item.call_count == 2


def test_clear_never_raises(caplog):
    client = MagicMock()
    client.delete_item.side_effect = _client_error()
    with caplog.at_level('WARNING'):
        assert clear_running_execution(client, TABLE, 'exec-1') is False
    assert 'exec-1' in caplog.text
    assert 'ProvisionedThroughputExceededException' in caplog.text


def _typed(record):
    return {k: {'S': v} for k, v in record.model_dump(exclude_none=True).items()}


def test_list_queries_the_partition_and_parses_records():
    client = MagicMock()
    a = new_running_execution(execution_id='exec-a', usecase_id='uc-1', microvm_id='vm-a', mode='batch',
                              max_duration_s=600, started_at=STARTED)
    b = new_running_execution(execution_id='exec-b', usecase_id='uc-2', microvm_id='vm-b', mode='wizard',
                              max_duration_s=600, started_at=STARTED, suite_execution_id='se-1')
    client.query.return_value = {'Items': [_typed(a), _typed(b)]}

    records = list_running_executions(client, TABLE)

    assert records == [a, b]
    client.query.assert_called_once_with(
        TableName=TABLE,
        KeyConditionExpression='pk = :pk',
        ExpressionAttributeValues={':pk': {'S': 'RUNNING_EXECUTIONS'}},
    )
    client.scan.assert_not_called()


def test_list_follows_pagination():
    client = MagicMock()
    a = new_running_execution(execution_id='exec-a', usecase_id='uc-1', microvm_id='vm-a', mode='batch',
                              max_duration_s=600, started_at=STARTED)
    b = new_running_execution(execution_id='exec-b', usecase_id='uc-1', microvm_id='vm-b', mode='batch',
                              max_duration_s=600, started_at=STARTED)
    client.query.side_effect = [
        {'Items': [_typed(a)], 'LastEvaluatedKey': {'pk': {'S': 'RUNNING_EXECUTIONS'}, 'sk': {'S': a.sk}}},
        {'Items': [_typed(b)]},
    ]

    records = list_running_executions(client, TABLE)

    assert [r.execution_id for r in records] == ['exec-a', 'exec-b']
    assert client.query.call_count == 2
    assert client.query.call_args_list[1].kwargs['ExclusiveStartKey'] == {
        'pk': {'S': 'RUNNING_EXECUTIONS'}, 'sk': {'S': a.sk}}
    assert 'ExclusiveStartKey' not in client.query.call_args_list[0].kwargs


def test_list_empty_partition():
    client = MagicMock()
    client.query.return_value = {'Items': []}
    assert list_running_executions(client, TABLE) == []
