"""``reconcile_executions``: scheduled sweep over ``RUNNING_EXECUTIONS``.

Decision table (one row per tracking record, in this order):

| VM lookup                           | deadline  | execution record | action                                   |
|-------------------------------------|-----------|------------------|------------------------------------------|
| any                                 | any       | already terminal | clear tracking record only (no write, no event) |
| any                                 | any       | missing          | clear tracking record only, log          |
| ``TERMINATED``                      | any       | non-terminal     | mark failed ``reconciler: microvm TERMINATED`` |
| ``ResourceNotFoundException``       | any       | non-terminal     | mark failed ``reconciler: microvm not found`` |
| RUNNING / PENDING / other           | passed    | non-terminal     | mark failed ``reconciler: deadline exceeded (state=<s>)`` |
| RUNNING / PENDING / other           | not yet   | —                | untouched                                |
| other exception                     | —         | —                | logged, record kept, loop continues      |

Metrics in ``QAStudio/Worker``: ``RunningMicrovms`` (VMs seen RUNNING/PENDING
after this pass) and ``ReconciledExecutions`` (marked failed this pass; 0 is
published too so the alarm has data).
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError

import reconcile_executions
from reconcile_executions import (
    METRIC_NAMESPACE,
    decide,
    handler,
)
from running_executions import DEADLINE_GRACE, new_running_execution

TABLE = 'test-table'
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', TABLE)
    monkeypatch.setenv('MICROVM_IMAGE_ARN', 'arn:aws:lambda:eu-central-1:123456789012:microvm-image:test-worker')


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(reconcile_executions, '_now', lambda: NOW)
    return NOW


def _record(execution_id='exec-1', usecase_id='uc-1', microvm_id='vm-1', *, started_minutes_ago=5,
            max_duration_s=3600, suite_execution_id=None):
    return new_running_execution(
        execution_id=execution_id, usecase_id=usecase_id, microvm_id=microvm_id, mode='batch',
        max_duration_s=max_duration_s, suite_execution_id=suite_execution_id,
        started_at=NOW - timedelta(minutes=started_minutes_ago),
    )


def _overdue_record(**kwargs):
    """Started long enough ago that ``deadline`` (duration + grace) is in the past."""
    minutes = 3600 // 60 + int(DEADLINE_GRACE.total_seconds() // 60) + 1
    return _record(started_minutes_ago=minutes, **kwargs)


def _execution_item(usecase_id='uc-1', execution_id='exec-1', status='running'):
    return {
        'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
        'sk': {'S': f'EXECUTION#{execution_id}'},
        'status': {'S': status},
    }


def _not_found():
    return ClientError({'Error': {'Code': 'ResourceNotFoundException', 'Message': 'gone'}}, 'GetMicrovm')


def _vm(state):
    return {'microvmId': 'vm-1', 'state': state}


class Harness:
    """Patch the module's AWS clients; expose the mocks and run the handler."""

    def __init__(self, records, *, vm_states=None, execution_items=None):
        self.ddb = MagicMock()
        self.eb = MagicMock()
        self.cw = MagicMock()
        self.vm = MagicMock()
        self.records = records
        vm_states = vm_states or {}
        execution_items = execution_items or {}

        def get_microvm(microvmIdentifier):
            result = vm_states.get(microvmIdentifier, _vm('RUNNING'))
            if isinstance(result, Exception):
                raise result
            return result

        self.vm.get_microvm.side_effect = get_microvm

        def get_item(TableName, Key):
            item = execution_items.get(Key['sk']['S'][len('EXECUTION#'):], 'DEFAULT')
            if item == 'DEFAULT':
                return {'Item': _execution_item(Key['pk']['S'][len('USECASE_EXECUTION#'):],
                                                Key['sk']['S'][len('EXECUTION#'):])}
            return {'Item': item} if item is not None else {}

        self.ddb.get_item.side_effect = get_item
        self.ddb.update_item.return_value = {'Attributes': {}}

    def run(self):
        with patch('reconcile_executions.dynamodb', self.ddb), \
             patch('reconcile_executions.eventbridge', self.eb), \
             patch('reconcile_executions.cloudwatch', self.cw), \
             patch('reconcile_executions.get_microvm_client', return_value=self.vm), \
             patch('reconcile_executions.list_running_executions', return_value=self.records), \
             patch('execution_transitions.cleanup_cache_artifacts') as self.cleanup, \
             patch('execution_transitions.boto3'):
            return handler({'source': 'aws.events'}, None)

    # -- assertions -------------------------------------------------------
    def status_writes(self):
        return [c.kwargs for c in self.ddb.update_item.call_args_list
                if c.kwargs['Key']['pk']['S'].startswith('USECASE_EXECUTION#')]

    def cleared(self):
        return [c.kwargs['Key']['sk']['S'][len('EXECUTION#'):] for c in self.ddb.delete_item.call_args_list]

    def metric(self, name):
        self.cw.put_metric_data.assert_called_once()
        kwargs = self.cw.put_metric_data.call_args.kwargs
        assert kwargs['Namespace'] == METRIC_NAMESPACE
        values = [m for m in kwargs['MetricData'] if m['MetricName'] == name]
        assert len(values) == 1, kwargs['MetricData']
        assert values[0]['Unit'] == 'Count'
        return values[0]['Value']


class TestDecide:
    def test_terminated_vm(self, clock):
        assert decide(_record(), _vm('TERMINATED'), clock) == 'microvm TERMINATED'

    def test_missing_vm(self, clock):
        assert decide(_record(), None, clock) == 'microvm not found'

    @pytest.mark.parametrize('state', ['RUNNING', 'PENDING', 'SUSPENDED'])
    def test_live_vm_before_deadline_is_healthy(self, clock, state):
        assert decide(_record(), _vm(state), clock) is None

    @pytest.mark.parametrize('state', ['RUNNING', 'PENDING', 'SUSPENDED'])
    def test_live_vm_past_deadline_is_overdue(self, clock, state):
        assert decide(_overdue_record(), _vm(state), clock) == f'deadline exceeded (state={state})'

    def test_terminated_wins_over_deadline(self, clock):
        assert decide(_overdue_record(), _vm('TERMINATED'), clock) == 'microvm TERMINATED'

    def test_deadline_is_exclusive(self, clock):
        record = _record()
        assert decide(record, _vm('RUNNING'), record.deadline_at()) is None
        assert decide(record, _vm('RUNNING'), record.deadline_at() + timedelta(seconds=1)) \
            == 'deadline exceeded (state=RUNNING)'


class TestHealthyVm:
    def test_running_vm_is_untouched(self, clock):
        h = Harness([_record()])
        summary = h.run()
        h.ddb.update_item.assert_not_called()
        h.ddb.delete_item.assert_not_called()
        h.eb.put_events.assert_not_called()
        h.cleanup.assert_not_called()
        # the execution record is not even read for a healthy VM
        h.ddb.get_item.assert_not_called()
        assert summary == {'checked': 1, 'reconciled': 0, 'cleared': 0, 'running': 1}

    def test_pending_vm_counts_as_running(self, clock):
        h = Harness([_record()], vm_states={'vm-1': _vm('PENDING')})
        assert h.run()['running'] == 1
        assert h.metric('RunningMicrovms') == 1

    def test_empty_partition_publishes_zeros(self, clock):
        h = Harness([])
        assert h.run() == {'checked': 0, 'reconciled': 0, 'cleared': 0, 'running': 0}
        assert h.metric('RunningMicrovms') == 0
        assert h.metric('ReconciledExecutions') == 0
        h.vm.get_microvm.assert_not_called()


class TestTerminatedVm:
    def test_marks_failed_through_the_shared_transition(self, clock):
        h = Harness([_record()], vm_states={'vm-1': _vm('TERMINATED')})
        summary = h.run()

        h.vm.get_microvm.assert_called_once_with(microvmIdentifier='vm-1')
        h.ddb.get_item.assert_called_once_with(
            TableName=TABLE, Key={'pk': {'S': 'USECASE_EXECUTION#uc-1'}, 'sk': {'S': 'EXECUTION#exec-1'}})

        writes = h.status_writes()
        assert len(writes) == 1
        vals = writes[0]['ExpressionAttributeValues']
        assert vals[':status'] == {'S': 'failed'}
        assert vals[':error_message'] == {'S': 'reconciler: microvm TERMINATED'}
        assert 'completed_at' in writes[0]['UpdateExpression']

        h.eb.put_events.assert_called_once()
        detail = json.loads(h.eb.put_events.call_args.kwargs['Entries'][0]['Detail'])
        assert detail == {'usecase_id': 'uc-1', 'execution_id': 'exec-1', 'status': 'failed',
                          'timestamp': detail['timestamp'], 'error_message': 'reconciler: microvm TERMINATED'}
        h.cleanup.assert_called_once()
        assert h.cleared() == ['exec-1']
        assert summary == {'checked': 1, 'reconciled': 1, 'cleared': 1, 'running': 0}
        assert h.metric('ReconciledExecutions') == 1
        assert h.metric('RunningMicrovms') == 0

    def test_suite_member_bumps_the_suite_counters(self, clock):
        h = Harness([_record(suite_execution_id='se-1')], vm_states={'vm-1': _vm('TERMINATED')})
        item = _execution_item()
        item['suite_execution_id'] = {'S': 'se-1'}
        item['suite_id'] = {'S': 's-1'}
        h = Harness([_record(suite_execution_id='se-1')], vm_states={'vm-1': _vm('TERMINATED')},
                    execution_items={'exec-1': item})
        h.run()
        suite_calls = [c.kwargs for c in h.ddb.update_item.call_args_list
                       if c.kwargs['Key']['pk']['S'] == 'SUITE_EXECUTION#s-1']
        assert len(suite_calls) == 1
        assert suite_calls[0]['UpdateExpression'] == \
            'ADD completed_usecases :inc, failed_usecases :inc, running_usecases :dec'

    def test_status_write_order_before_clear(self, clock):
        h = Harness([_record()], vm_states={'vm-1': _vm('TERMINATED')})
        h.run()
        names = [c[0] for c in h.ddb.method_calls if c[0] in ('update_item', 'delete_item')]
        assert names.index('update_item') < names.index('delete_item')


class TestMissingVm:
    def test_resource_not_found_is_reconciled(self, clock):
        h = Harness([_record()], vm_states={'vm-1': _not_found()})
        summary = h.run()
        writes = h.status_writes()
        assert len(writes) == 1
        assert writes[0]['ExpressionAttributeValues'][':error_message'] == {'S': 'reconciler: microvm not found'}
        h.eb.put_events.assert_called_once()
        assert h.cleared() == ['exec-1']
        assert summary['reconciled'] == 1 and summary['running'] == 0


class TestDeadline:
    def test_running_vm_past_deadline_is_reconciled(self, clock):
        h = Harness([_overdue_record()])
        summary = h.run()
        writes = h.status_writes()
        assert len(writes) == 1
        assert writes[0]['ExpressionAttributeValues'][':error_message'] == \
            {'S': 'reconciler: deadline exceeded (state=RUNNING)'}
        assert h.cleared() == ['exec-1']
        # the VM is still alive, so it still counts towards RunningMicrovms
        assert summary == {'checked': 1, 'reconciled': 1, 'cleared': 1, 'running': 1}
        assert h.metric('RunningMicrovms') == 1

    def test_before_deadline_untouched(self, clock):
        h = Harness([_record(max_duration_s=600, started_minutes_ago=15)])  # deadline = 10 + 10 grace
        assert h.run()['reconciled'] == 0
        h.ddb.update_item.assert_not_called()


class TestAlreadyTerminal:
    @pytest.mark.parametrize('status', ['success', 'failed', 'stopped', 'error', 'completed', 'timeout'])
    def test_only_the_tracking_record_is_cleared(self, clock, status):
        h = Harness([_record()], vm_states={'vm-1': _vm('TERMINATED')},
                    execution_items={'exec-1': _execution_item(status=status)})
        summary = h.run()
        h.ddb.update_item.assert_not_called()
        h.eb.put_events.assert_not_called()
        h.cleanup.assert_not_called()
        assert h.cleared() == ['exec-1']
        assert summary == {'checked': 1, 'reconciled': 0, 'cleared': 1, 'running': 0}
        assert h.metric('ReconciledExecutions') == 0

    def test_timed_out_wizard_session_is_not_marked_failed(self, clock):
        """``wizard_worker.py`` writes ``timeout`` itself on inactivity and the
        VM then self-terminates; the reconciler must not fire the alarm for it."""
        h = Harness([_record()], vm_states={'vm-1': _vm('TERMINATED')},
                    execution_items={'exec-1': _execution_item(status='timeout')})
        summary = h.run()
        assert h.status_writes() == []
        h.eb.put_events.assert_not_called()
        assert h.cleared() == ['exec-1']
        assert summary['reconciled'] == 0
        assert h.metric('ReconciledExecutions') == 0

    def test_missing_execution_record_is_cleared_and_logged(self, clock, caplog):
        h = Harness([_record()], vm_states={'vm-1': _vm('TERMINATED')}, execution_items={'exec-1': None})
        with caplog.at_level(logging.WARNING, logger='reconcile_executions'):
            summary = h.run()
        h.ddb.update_item.assert_not_called()
        h.eb.put_events.assert_not_called()
        assert h.cleared() == ['exec-1']
        assert summary == {'checked': 1, 'reconciled': 0, 'cleared': 1, 'running': 0}
        assert any('exec-1' in r.message and 'not found' in r.message for r in caplog.records)


class TestIsolation:
    def test_one_failing_record_does_not_stop_the_others(self, clock, caplog):
        records = [
            _record(execution_id='exec-boom', microvm_id='vm-boom'),
            _record(execution_id='exec-dead', microvm_id='vm-dead'),
            _record(execution_id='exec-ok', microvm_id='vm-ok'),
        ]
        h = Harness(records, vm_states={
            'vm-boom': ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'slow'}}, 'GetMicrovm'),
            'vm-dead': _vm('TERMINATED'),
        })
        with caplog.at_level(logging.ERROR, logger='reconcile_executions'):
            summary = h.run()
        assert h.cleared() == ['exec-dead']
        assert len(h.status_writes()) == 1
        assert summary == {'checked': 3, 'reconciled': 1, 'cleared': 1, 'running': 1}
        assert any('exec-boom' in r.message for r in caplog.records)
        # an unknown-state VM that errored is neither running nor reconciled
        assert h.metric('RunningMicrovms') == 1

    def test_status_write_failure_keeps_the_record_and_continues(self, clock, caplog):
        records = [_record(execution_id='exec-a', microvm_id='vm-a'), _record(execution_id='exec-b', microvm_id='vm-b')]
        h = Harness(records, vm_states={'vm-a': _vm('TERMINATED'), 'vm-b': _vm('TERMINATED')})
        h.ddb.update_item.side_effect = [
            ClientError({'Error': {'Code': 'InternalServerError', 'Message': 'x'}}, 'UpdateItem'),
            {'Attributes': {}},
        ]
        with caplog.at_level(logging.ERROR, logger='reconcile_executions'):
            summary = h.run()
        # exec-a: write failed → no finalize, tracking record kept for the next pass
        assert h.cleared() == ['exec-b']
        assert summary == {'checked': 2, 'reconciled': 1, 'cleared': 1, 'running': 0}
        assert any('exec-a' in r.message for r in caplog.records)

    def test_metric_publish_failure_does_not_fail_the_run(self, clock):
        h = Harness([_record()])
        h.cw.put_metric_data.side_effect = Exception('cw down')
        assert h.run()['checked'] == 1


class TestSummaryLog:
    def test_summary_is_logged_as_one_json_line(self, clock, caplog):
        h = Harness([_record()], vm_states={'vm-1': _vm('TERMINATED')})
        with caplog.at_level(logging.INFO, logger='reconcile_executions'):
            summary = h.run()
        lines = [r.message for r in caplog.records if r.message.startswith('{')]
        assert len(lines) == 1
        assert json.loads(lines[0]) == {'event': 'reconcile_executions', **summary}


class TestMetricsShape:
    def test_both_metrics_in_one_call_with_timestamps(self, clock):
        h = Harness([_record()])
        h.run()
        data = h.cw.put_metric_data.call_args.kwargs['MetricData']
        assert sorted(m['MetricName'] for m in data) == ['ReconciledExecutions', 'RunningMicrovms']
        for m in data:
            assert m['Timestamp'] == NOW
            assert 'Dimensions' not in m


class TestClientPlumbing:
    def test_module_import_does_not_construct_the_microvm_client(self):
        import importlib
        with patch('boto3.client') as make_client:
            reloaded = importlib.reload(reconcile_executions)
        # dynamodb / events / cloudwatch are module-level; lambda-microvms is not
        assert call('lambda-microvms') not in make_client.call_args_list
        assert reloaded is not None
