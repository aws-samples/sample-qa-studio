"""``execution_transitions``: the one terminal-transition implementation.

``update_execution_status`` (API) and ``reconcile_executions`` (scheduled)
both call it, so the EventBridge event, cache cleanup, suite counters, suite
completion, test-suite summary and tracking-record delete behave identically
whichever side reports the failure.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

import execution_transitions
from execution_transitions import (
    TERMINAL_STATUSES,
    finalize_terminal_transition,
    mark_execution_failed,
    record_microvm_runtime,
)

TABLE = 'test-table'
MICROVM_ID = 'mvm-0123456789abcdef0'
STARTED = datetime(2026, 11, 5, 8, 0, 3, tzinfo=timezone.utc)
TERMINATED = datetime(2026, 11, 5, 8, 21, 47, tzinfo=timezone.utc)
EXECUTION_KEY = {'pk': {'S': 'USECASE_EXECUTION#uc-1'}, 'sk': {'S': 'EXECUTION#exec-1'}}


def _microvms(**response):
    """Fake ``lambda-microvms`` client answering ``get_microvm`` with ``response``."""
    client = MagicMock(name='lambda-microvms')
    client.get_microvm.return_value = {'microvmId': MICROVM_ID, **response}
    return client


def _runtime_write(ddb):
    """kwargs of the ``microvm_started_at`` / ``microvm_terminated_at`` write, or None."""
    for call in ddb.update_item.call_args_list:
        if 'microvm_started_at' in call.kwargs.get('UpdateExpression', ''):
            return call.kwargs
    return None


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', TABLE)
    monkeypatch.delenv('S3_BUCKET', raising=False)


def _item(usecase_id='uc-1', execution_id='exec-1', status='running', suite=False, microvm_id=None):
    item = {
        'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
        'sk': {'S': f'EXECUTION#{execution_id}'},
        'status': {'S': status},
    }
    if suite:
        item['suite_execution_id'] = {'S': 'se-1'}
        item['suite_id'] = {'S': 's-1'}
    if microvm_id:
        item['microvm_id'] = {'S': microvm_id}
    return item


def _suite_counter_call(ddb, suite_id='s-1'):
    for call in ddb.update_item.call_args_list:
        if call.kwargs['Key']['pk']['S'] == f'SUITE_EXECUTION#{suite_id}':
            return call.kwargs
    return None


class TestTerminalStatuses:
    def test_matches_the_status_guard_set(self):
        assert TERMINAL_STATUSES == frozenset({'success', 'failed', 'stopped', 'error', 'completed', 'timeout'})

    def test_timeout_is_terminal(self):
        """The wizard worker's inactivity path writes ``timeout`` directly; the
        reconciler must not turn it into ``failed`` (and fire the alarm)."""
        assert 'timeout' in TERMINAL_STATUSES

    def test_timeout_does_not_move_suite_counters_or_the_cache(self):
        ddb, eb = MagicMock(), MagicMock()
        with patch('execution_transitions.cleanup_cache_artifacts') as cleanup:
            finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'timeout', _item(suite=True))
        cleanup.assert_not_called()
        ddb.update_item.assert_not_called()
        ddb.delete_item.assert_called_once()  # tracking record still cleared
        eb.put_events.assert_called_once()


class TestFinalizeTerminalTransition:
    def test_publishes_the_status_changed_event(self):
        ddb, eb = MagicMock(), MagicMock()
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item())
        eb.put_events.assert_called_once()
        entry = eb.put_events.call_args.kwargs['Entries'][0]
        assert entry['Source'] == 'nova-act-qa-studio.execution'
        assert entry['DetailType'] == 'nova-act-qa-studio.execution.status.changed'
        assert entry['EventBusName'] == 'default'
        detail = json.loads(entry['Detail'])
        assert detail['usecase_id'] == 'uc-1'
        assert detail['execution_id'] == 'exec-1'
        assert detail['status'] == 'success'
        assert 'timestamp' in detail
        assert 'error_message' not in detail

    def test_event_carries_the_error_message_when_given(self):
        ddb, eb = MagicMock(), MagicMock()
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'failed', _item(), error_message='boom')
        detail = json.loads(eb.put_events.call_args.kwargs['Entries'][0]['Detail'])
        assert detail['error_message'] == 'boom'

    def test_event_publish_failure_is_swallowed(self):
        ddb, eb = MagicMock(), MagicMock()
        eb.put_events.side_effect = Exception('bus down')
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item())

    def test_clears_the_running_execution_record(self):
        ddb, eb = MagicMock(), MagicMock()
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item())
        ddb.delete_item.assert_called_once_with(
            TableName=TABLE, Key={'pk': {'S': 'RUNNING_EXECUTIONS'}, 'sk': {'S': 'EXECUTION#exec-1'}})

    def test_clear_failure_is_swallowed(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.delete_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'slow'}}, 'DeleteItem')
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item())

    def test_failed_wipes_the_usecase_cache(self):
        ddb, eb = MagicMock(), MagicMock()
        with patch('execution_transitions.cleanup_cache_artifacts') as cleanup, \
             patch('execution_transitions.boto3') as boto:
            finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'failed', _item())
        cleanup.assert_called_once()
        table_arg, usecase_arg, bucket_arg = cleanup.call_args.args
        assert usecase_arg == 'uc-1'
        assert bucket_arg == ''
        boto.resource.assert_called_once_with('dynamodb')
        boto.resource.return_value.Table.assert_called_once_with(TABLE)
        assert table_arg is boto.resource.return_value.Table.return_value

    def test_cache_cleanup_reads_the_bucket_from_the_environment(self, monkeypatch):
        monkeypatch.setenv('S3_BUCKET', 'my-bucket')
        ddb, eb = MagicMock(), MagicMock()
        with patch('execution_transitions.cleanup_cache_artifacts') as cleanup, \
             patch('execution_transitions.boto3'):
            finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'failed', _item())
        assert cleanup.call_args.args[2] == 'my-bucket'

    @pytest.mark.parametrize('status', ['success', 'completed', 'stopped', 'error'])
    def test_other_statuses_keep_the_cache(self, status):
        ddb, eb = MagicMock(), MagicMock()
        with patch('execution_transitions.cleanup_cache_artifacts') as cleanup:
            finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', status, _item())
        cleanup.assert_not_called()

    def test_cache_cleanup_failure_is_swallowed(self):
        ddb, eb = MagicMock(), MagicMock()
        with patch('execution_transitions.cleanup_cache_artifacts', side_effect=Exception('s3 down')), \
             patch('execution_transitions.boto3'):
            finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'failed', _item())

    def test_success_increments_suite_counters(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.return_value = {'Attributes': {}}
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item(suite=True))
        call = _suite_counter_call(ddb)
        assert call is not None
        assert call['UpdateExpression'] == 'ADD completed_usecases :inc, successful_usecases :inc, running_usecases :dec'
        assert call['Key'] == {'pk': {'S': 'SUITE_EXECUTION#s-1'}, 'sk': {'S': 'EXECUTION#se-1'}}
        assert call['ExpressionAttributeValues'] == {':inc': {'N': '1'}, ':dec': {'N': '-1'}}
        assert call['ReturnValues'] == 'ALL_NEW'

    def test_failed_increments_suite_failed_counter(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.return_value = {'Attributes': {}}
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'failed', _item(suite=True))
        call = _suite_counter_call(ddb)
        assert call['UpdateExpression'] == 'ADD completed_usecases :inc, failed_usecases :inc, running_usecases :dec'

    @pytest.mark.parametrize('status', ['completed', 'stopped', 'error'])
    def test_other_terminal_statuses_do_not_count(self, status):
        ddb, eb = MagicMock(), MagicMock()
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', status, _item(suite=True))
        ddb.update_item.assert_not_called()

    def test_no_suite_membership_no_counter_write(self):
        ddb, eb = MagicMock(), MagicMock()
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item())
        ddb.update_item.assert_not_called()

    def test_last_usecase_finalizes_the_suite_execution_and_summary(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.return_value = {'Attributes': {
            'total_usecases': {'N': '2'}, 'completed_usecases': {'N': '2'},
            'failed_usecases': {'N': '1'}, 'successful_usecases': {'N': '1'},
            'started_at': {'S': '2026-01-01T00:00:00Z'},
        }}
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'failed', _item(suite=True))
        calls = [c.kwargs for c in ddb.update_item.call_args_list]
        assert len(calls) == 3
        finalize = calls[1]
        assert finalize['Key'] == {'pk': {'S': 'SUITE_EXECUTION#s-1'}, 'sk': {'S': 'EXECUTION#se-1'}}
        assert finalize['UpdateExpression'] == 'SET #status = :status, completed_at = :completed_at, duration_ms = :duration'
        assert finalize['ExpressionAttributeValues'][':status'] == {'S': 'failed'}
        assert int(finalize['ExpressionAttributeValues'][':duration']['N']) > 0
        summary = calls[2]
        assert summary['Key'] == {'pk': {'S': 'TEST_SUITES'}, 'sk': {'S': 'SUITE#s-1'}}
        vals = summary['ExpressionAttributeValues']
        assert vals[':status'] == {'S': 'failed'}
        assert vals[':exec_id'] == {'S': 'se-1'}
        assert vals[':successful'] == {'N': '1'}
        assert vals[':failed'] == {'N': '1'}

    def test_all_successful_finalizes_as_completed(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.return_value = {'Attributes': {
            'total_usecases': {'N': '1'}, 'completed_usecases': {'N': '1'},
            'failed_usecases': {'N': '0'}, 'successful_usecases': {'N': '1'},
        }}
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item(suite=True))
        finalize = ddb.update_item.call_args_list[1].kwargs
        assert finalize['ExpressionAttributeValues'][':status'] == {'S': 'completed'}
        assert finalize['ExpressionAttributeValues'][':duration'] == {'N': '0'}

    def test_incomplete_suite_is_not_finalized(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.return_value = {'Attributes': {
            'total_usecases': {'N': '3'}, 'completed_usecases': {'N': '1'}}}
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item(suite=True))
        assert ddb.update_item.call_count == 1

    def test_suite_counter_failure_is_swallowed(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.side_effect = Exception('throttle')
        finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item(suite=True))
        eb.put_events.assert_called_once()
        ddb.delete_item.assert_called_once()


class TestRecordMicrovmRuntime:
    """``GetMicrovm`` once, two attributes on the execution record, never raises."""

    def test_writes_started_and_terminated_from_the_vm(self):
        ddb = MagicMock()
        microvms = _microvms(state='TERMINATED', startedAt=STARTED, terminatedAt=TERMINATED)

        assert record_microvm_runtime(ddb, microvms, TABLE, 'uc-1', 'exec-1', MICROVM_ID) is True

        microvms.get_microvm.assert_called_once_with(microvmIdentifier=MICROVM_ID)
        ddb.update_item.assert_called_once_with(
            TableName=TABLE,
            Key=EXECUTION_KEY,
            UpdateExpression='SET microvm_started_at = :started_at, microvm_terminated_at = :terminated_at',
            ExpressionAttributeValues={
                ':started_at': {'S': '2026-11-05T08:00:03Z'},
                ':terminated_at': {'S': '2026-11-05T08:21:47Z'},
            },
        )

    def test_timestamps_are_normalised_to_utc(self):
        ddb = MagicMock()
        plus_two = timezone(timedelta(hours=2))
        microvms = _microvms(state='TERMINATED',
                             startedAt=STARTED.astimezone(plus_two), terminatedAt=TERMINATED.astimezone(plus_two))
        record_microvm_runtime(ddb, microvms, TABLE, 'uc-1', 'exec-1', MICROVM_ID)
        vals = ddb.update_item.call_args.kwargs['ExpressionAttributeValues']
        assert vals[':started_at'] == {'S': '2026-11-05T08:00:03Z'}
        assert vals[':terminated_at'] == {'S': '2026-11-05T08:21:47Z'}

    def test_missing_terminated_at_uses_now(self):
        """Right after ``stop_execution`` the VM is still RUNNING / TERMINATING."""
        ddb = MagicMock()
        microvms = _microvms(state='RUNNING', startedAt=STARTED)
        with patch('execution_transitions.get_current_timestamp', return_value='2026-11-05T08:30:00Z'):
            assert record_microvm_runtime(ddb, microvms, TABLE, 'uc-1', 'exec-1', MICROVM_ID) is True
        vals = ddb.update_item.call_args.kwargs['ExpressionAttributeValues']
        assert vals[':started_at'] == {'S': '2026-11-05T08:00:03Z'}
        assert vals[':terminated_at'] == {'S': '2026-11-05T08:30:00Z'}

    def test_missing_started_at_writes_nothing(self, caplog):
        """A VM that never left PENDING has no runtime; both fields or neither."""
        ddb = MagicMock()
        microvms = _microvms(state='PENDING')
        with caplog.at_level(logging.WARNING, logger='execution_transitions'):
            assert record_microvm_runtime(ddb, microvms, TABLE, 'uc-1', 'exec-1', MICROVM_ID) is False
        ddb.update_item.assert_not_called()
        assert 'startedAt' in caplog.text

    @pytest.mark.parametrize('error', [
        ClientError({'Error': {'Code': 'ResourceNotFoundException', 'Message': 'gone'}}, 'GetMicrovm'),
        ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'GetMicrovm'),
        BotoCoreError(),
    ], ids=['not found', 'access denied', 'botocore'])
    def test_get_microvm_error_is_logged_and_nothing_is_written(self, error, caplog):
        ddb = MagicMock()
        microvms = MagicMock()
        microvms.get_microvm.side_effect = error
        with caplog.at_level(logging.WARNING, logger='execution_transitions'):
            assert record_microvm_runtime(ddb, microvms, TABLE, 'uc-1', 'exec-1', MICROVM_ID) is False
        ddb.update_item.assert_not_called()
        record = next(r for r in caplog.records if r.levelno == logging.WARNING)
        assert MICROVM_ID in record.getMessage()
        assert 'exec-1' in record.getMessage()

    def test_write_failure_is_logged_and_swallowed(self, caplog):
        ddb = MagicMock()
        ddb.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'slow'}}, 'UpdateItem')
        microvms = _microvms(state='TERMINATED', startedAt=STARTED, terminatedAt=TERMINATED)
        with caplog.at_level(logging.WARNING, logger='execution_transitions'):
            assert record_microvm_runtime(ddb, microvms, TABLE, 'uc-1', 'exec-1', MICROVM_ID) is False
        assert any(r.levelno == logging.WARNING for r in caplog.records)


class TestFinalizeRecordsMicrovmRuntime:
    """``finalize_terminal_transition`` records the VM runtime first, through the shared client."""

    def test_vm_runtime_is_written_before_the_tracking_record_delete(self):
        ddb, eb = MagicMock(), MagicMock()
        microvms = _microvms(state='TERMINATED', startedAt=STARTED, terminatedAt=TERMINATED)
        with patch('execution_transitions.get_microvm_client', return_value=microvms) as get_client:
            finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item(microvm_id=MICROVM_ID))
        get_client.assert_called_once_with()
        microvms.get_microvm.assert_called_once_with(microvmIdentifier=MICROVM_ID)
        write = _runtime_write(ddb)
        assert write is not None
        assert write['Key'] == EXECUTION_KEY
        names = [c[0] for c in ddb.method_calls if c[0] in ('update_item', 'delete_item')]
        assert names == ['update_item', 'delete_item']
        eb.put_events.assert_called_once()

    def test_item_without_microvm_id_never_touches_the_microvm_client(self):
        ddb, eb = MagicMock(), MagicMock()
        with patch('execution_transitions.get_microvm_client') as get_client:
            finalize_terminal_transition(ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item())
        get_client.assert_not_called()
        assert _runtime_write(ddb) is None

    def test_vm_not_found_still_completes_the_transition(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.return_value = {'Attributes': {}}
        microvms = MagicMock()
        microvms.get_microvm.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'gone'}}, 'GetMicrovm')
        with patch('execution_transitions.get_microvm_client', return_value=microvms):
            finalize_terminal_transition(
                ddb, eb, TABLE, 'uc-1', 'exec-1', 'success', _item(suite=True, microvm_id=MICROVM_ID))
        assert _runtime_write(ddb) is None
        ddb.delete_item.assert_called_once()
        eb.put_events.assert_called_once()
        assert _suite_counter_call(ddb) is not None

    def test_mark_execution_failed_records_the_runtime_of_the_reconciled_vm(self):
        ddb, eb = MagicMock(), MagicMock()
        microvms = _microvms(state='TERMINATED', startedAt=STARTED, terminatedAt=TERMINATED)
        with patch('execution_transitions.get_microvm_client', return_value=microvms):
            mark_execution_failed(ddb, eb, TABLE, 'uc-1', 'exec-1', 'reconciler: microvm TERMINATED',
                                  _item(microvm_id=MICROVM_ID))
        expressions = [c.kwargs['UpdateExpression'] for c in ddb.update_item.call_args_list]
        assert expressions[0].startswith('SET #status = :status')
        assert expressions[1] == 'SET microvm_started_at = :started_at, microvm_terminated_at = :terminated_at'


class TestMarkExecutionFailed:
    def test_writes_failed_with_completed_at_and_error_message(self):
        ddb, eb = MagicMock(), MagicMock()
        with patch.object(execution_transitions, 'finalize_terminal_transition') as finalize:
            mark_execution_failed(ddb, eb, TABLE, 'uc-1', 'exec-1', 'reconciler: microvm TERMINATED', _item())
        ddb.update_item.assert_called_once()
        kwargs = ddb.update_item.call_args.kwargs
        assert kwargs['TableName'] == TABLE
        assert kwargs['Key'] == {'pk': {'S': 'USECASE_EXECUTION#uc-1'}, 'sk': {'S': 'EXECUTION#exec-1'}}
        assert kwargs['UpdateExpression'] == (
            'SET #status = :status, updated_at = :updated_at, completed_at = :completed_at, '
            'error_message = :error_message')
        assert kwargs['ExpressionAttributeNames'] == {'#status': 'status'}
        vals = kwargs['ExpressionAttributeValues']
        assert vals[':status'] == {'S': 'failed'}
        assert vals[':error_message'] == {'S': 'reconciler: microvm TERMINATED'}
        assert vals[':updated_at'] == vals[':completed_at']
        finalize.assert_called_once_with(
            ddb, eb, TABLE, 'uc-1', 'exec-1', 'failed', _item(), error_message='reconciler: microvm TERMINATED')

    def test_status_write_failure_propagates_and_skips_finalize(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'no'}}, 'UpdateItem')
        with patch.object(execution_transitions, 'finalize_terminal_transition') as finalize, \
             pytest.raises(ClientError):
            mark_execution_failed(ddb, eb, TABLE, 'uc-1', 'exec-1', 'x', _item())
        finalize.assert_not_called()

    def test_end_to_end_with_suite_and_cache(self):
        ddb, eb = MagicMock(), MagicMock()
        ddb.update_item.return_value = {'Attributes': {}}
        with patch('execution_transitions.cleanup_cache_artifacts') as cleanup, \
             patch('execution_transitions.boto3'):
            mark_execution_failed(ddb, eb, TABLE, 'uc-1', 'exec-1', 'reconciler: microvm not found', _item(suite=True))
        assert ddb.update_item.call_count == 2  # status write + suite counters
        assert _suite_counter_call(ddb) is not None
        cleanup.assert_called_once()
        eb.put_events.assert_called_once()
        detail = json.loads(eb.put_events.call_args.kwargs['Entries'][0]['Detail'])
        assert detail['status'] == 'failed'
        assert detail['error_message'] == 'reconciler: microvm not found'
        ddb.delete_item.assert_called_once()
        names = [c[0] for c in ddb.method_calls if c[0] in ('update_item', 'delete_item')]
        assert names.index('update_item') < names.index('delete_item')
