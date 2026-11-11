"""stop_execution Lambda: MicroVM stop path.

An execution record carries ``microvm_id``.  The handler writes ``stopped``
*before* calling ``TerminateMicrovm`` so the runner's SIGTERM handler finds a
terminal record and its late ``failed`` PATCH is rejected, then records the
VM's start/termination time on the execution record (``GetMicrovm``; the VM is
still winding down, so ``microvm_terminated_at`` is *now*) and clears the
``RUNNING_EXECUTIONS`` item.  Records of the removed ECS runtime (``task_arn``
only) are rejected with 400.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from authz_test_support import make_event, resource_access_granted
from fake_table import FakeTable
from stop_execution import handler

UC_ID = 'uc-stop-1'
EXEC_ID = 'exec-stop-1'
EXECUTION_KEY = {'pk': f'USECASE_EXECUTION#{UC_ID}', 'sk': f'EXECUTION#{EXEC_ID}'}
TYPED_EXECUTION_KEY = {'pk': {'S': EXECUTION_KEY['pk']}, 'sk': {'S': EXECUTION_KEY['sk']}}
TASK_ARN = 'arn:aws:ecs:eu-central-1:123456789012:task/test-cluster/task-1'
MICROVM_ID = 'vm-0123456789abcdef'
VM_STARTED = datetime(2026, 11, 5, 8, 0, 3, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env_and_access(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 'test-table')
    with resource_access_granted():
        yield


def _event():
    return make_event('executor_a', path={'id': UC_ID, 'executionId': EXEC_ID})


class _Harness:
    """``stop_execution.boto3`` stand-in: a FakeTable behind ``resource('dynamodb')``
    and one MagicMock per ``client(<service>)``; ``calls`` records the order of
    the execution-record update and the terminate call."""

    def __init__(self, items):
        self.table = FakeTable(items)
        self.calls = []
        self.microvms = MagicMock(name='lambda-microvms')
        self.dynamodb_client = MagicMock(name='dynamodb')
        self.boto3 = MagicMock(name='boto3')
        self.boto3.resource.return_value.Table.return_value = self.table
        self.boto3.client.side_effect = self._client

        original_update = self.table.update_item

        def recording_update(**kwargs):
            self.calls.append(('update_item', kwargs['ExpressionAttributeValues'].get(':status')))
            return original_update(**kwargs)

        self.table.update_item = recording_update
        self.microvms.terminate_microvm.side_effect = (
            lambda **kw: self.calls.append(('terminate_microvm', kw['microvmIdentifier'])) or {})
        # Right after TerminateMicrovm the VM is still RUNNING: no terminatedAt yet.
        self.microvms.get_microvm.side_effect = (
            lambda **kw: self.calls.append(('get_microvm', kw['microvmIdentifier'])) or {
                'microvmId': kw['microvmIdentifier'], 'state': 'RUNNING', 'startedAt': VM_STARTED})
        self.dynamodb_client.update_item.side_effect = (
            lambda **kw: self.calls.append(('record_runtime', kw['Key'])) or {})

    def _client(self, service, **_):
        return {'lambda-microvms': self.microvms, 'dynamodb': self.dynamodb_client}[service]

    def microvm_client_requests(self):
        return [c for c in self.boto3.client.call_args_list if c.args[0] == 'lambda-microvms']

    def runtime_write(self):
        """kwargs of the ``microvm_started_at`` / ``microvm_terminated_at`` write on the low-level client."""
        return self.dynamodb_client.update_item.call_args.kwargs if self.dynamodb_client.update_item.called else None


def _run(items):
    harness = _Harness(items)
    with patch('stop_execution.boto3', harness.boto3):
        response = handler(_event(), None)
    return response, harness


def _record(**extra):
    return {**EXECUTION_KEY, 'status': 'running', **extra}


# ---------------------------------------------------------------------------
# MicroVM path
# ---------------------------------------------------------------------------

def test_microvm_execution_is_marked_stopped_then_terminated():
    response, h = _run([_record(microvm_id=MICROVM_ID)])

    assert response['statusCode'] == 200, response['body']
    body = json.loads(response['body'])
    assert body['status'] == 'stopped'
    assert body['executionId'] == EXEC_ID
    assert body['microvmId'] == MICROVM_ID
    assert 'taskArn' not in body
    assert body['stoppedAt']

    # stopped is written FIRST, then the VM is terminated, then its runtime is recorded
    assert h.calls == [
        ('update_item', 'stopped'),
        ('terminate_microvm', MICROVM_ID),
        ('get_microvm', MICROVM_ID),
        ('record_runtime', TYPED_EXECUTION_KEY),
    ]
    h.microvms.terminate_microvm.assert_called_once_with(microvmIdentifier=MICROVM_ID)

    stored = h.table.get(**EXECUTION_KEY)
    assert stored['status'] == 'stopped'
    assert stored['completed_at'] == body['stoppedAt']


def test_microvm_runtime_is_recorded_with_now_as_termination():
    _, h = _run([_record(microvm_id=MICROVM_ID)])

    h.microvms.get_microvm.assert_called_once_with(microvmIdentifier=MICROVM_ID)
    write = h.runtime_write()
    assert write['TableName'] == 'test-table'
    assert write['Key'] == TYPED_EXECUTION_KEY
    assert write['UpdateExpression'] == 'SET microvm_started_at = :started_at, microvm_terminated_at = :terminated_at'
    vals = write['ExpressionAttributeValues']
    assert vals[':started_at'] == {'S': '2026-11-05T08:00:03Z'}
    # the VM has no terminatedAt yet → the stop time stands in
    stopped_at = h.table.get(**EXECUTION_KEY)['completed_at']
    assert vals[':terminated_at']['S'] >= stopped_at


def test_vm_already_terminated_records_its_own_terminated_at():
    harness = _Harness([_record(microvm_id=MICROVM_ID)])
    harness.microvms.get_microvm.side_effect = None
    harness.microvms.get_microvm.return_value = {
        'state': 'TERMINATED', 'startedAt': VM_STARTED,
        'terminatedAt': datetime(2026, 11, 5, 8, 10, 0, tzinfo=timezone.utc)}
    with patch('stop_execution.boto3', harness.boto3):
        response = handler(_event(), None)
    assert response['statusCode'] == 200
    assert harness.runtime_write()['ExpressionAttributeValues'][':terminated_at'] == {'S': '2026-11-05T08:10:00Z'}


@pytest.mark.parametrize('error', [
    ClientError({'Error': {'Code': 'ResourceNotFoundException', 'Message': 'gone'}}, 'GetMicrovm'),
    ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'GetMicrovm'),
    BotoCoreError(),
])
def test_get_microvm_error_writes_no_runtime_and_the_stop_succeeds(error):
    harness = _Harness([_record(microvm_id=MICROVM_ID)])
    harness.microvms.get_microvm.side_effect = error
    with patch('stop_execution.boto3', harness.boto3):
        response = handler(_event(), None)

    assert response['statusCode'] == 200, response['body']
    assert harness.runtime_write() is None
    assert harness.table.get(**EXECUTION_KEY)['status'] == 'stopped'
    harness.dynamodb_client.delete_item.assert_called_once()


def test_microvm_client_is_created_lazily_only_when_a_vm_is_terminated():
    _, h = _run([_record(microvm_id=MICROVM_ID)])
    assert len(h.microvm_client_requests()) == 1  # one client for TerminateMicrovm and GetMicrovm
    h.microvms.terminate_microvm.assert_called_once()
    h.microvms.get_microvm.assert_called_once()

    _, h = _run([_record(task_arn=TASK_ARN)])
    assert h.microvm_client_requests() == []


@pytest.mark.parametrize('error', [
    ClientError({'Error': {'Code': 'ResourceNotFoundException', 'Message': 'gone'}}, 'TerminateMicrovm'),
    ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'TerminateMicrovm'),
    BotoCoreError(),
])
def test_terminate_error_is_tolerated_and_the_record_stays_stopped(error):
    harness = _Harness([_record(microvm_id=MICROVM_ID)])
    harness.microvms.terminate_microvm.side_effect = error
    with patch('stop_execution.boto3', harness.boto3):
        response = handler(_event(), None)

    assert response['statusCode'] == 200, response['body']
    assert json.loads(response['body'])['microvmId'] == MICROVM_ID
    assert harness.table.get(**EXECUTION_KEY)['status'] == 'stopped'


def test_microvm_path_clears_the_running_execution_record_after_stopped():
    _, h = _run([_record(microvm_id=MICROVM_ID)])

    h.dynamodb_client.delete_item.assert_called_once_with(
        TableName='test-table',
        Key={'pk': {'S': 'RUNNING_EXECUTIONS'}, 'sk': {'S': f'EXECUTION#{EXEC_ID}'}},
    )
    assert h.calls[0] == ('update_item', 'stopped')


def test_running_execution_clear_failure_does_not_fail_the_stop():
    harness = _Harness([_record(microvm_id=MICROVM_ID)])
    harness.dynamodb_client.delete_item.side_effect = ClientError(
        {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'slow'}}, 'DeleteItem')
    with patch('stop_execution.boto3', harness.boto3):
        response = handler(_event(), None)

    assert response['statusCode'] == 200, response['body']
    assert json.loads(response['body'])['microvmId'] == MICROVM_ID
    assert harness.table.get(**EXECUTION_KEY)['status'] == 'stopped'


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('identifier', [{}, {'task_arn': TASK_ARN}], ids=['no identifier', 'legacy ECS task_arn'])
def test_execution_without_microvm_is_400_and_nothing_is_called(identifier):
    """Legacy ECS records (``task_arn`` only) can no longer be stopped: the ECS runtime is gone."""
    response, h = _run([_record(**identifier)])

    assert response['statusCode'] == 400
    assert json.loads(response['body'])['error'] == 'execution has no associated MicroVM'
    assert h.calls == []
    h.microvms.terminate_microvm.assert_not_called()
    assert h.table.get(**EXECUTION_KEY)['status'] == 'running'


@pytest.mark.parametrize('status', ['success', 'failed', 'stopped', 'error'])
def test_terminal_execution_is_400_and_nothing_is_called(status):
    response, h = _run([_record(status=status, microvm_id=MICROVM_ID)])

    assert response['statusCode'] == 400
    assert json.loads(response['body'])['error'] == f'execution is already in terminal state: {status}'
    assert h.calls == []
    h.dynamodb_client.delete_item.assert_not_called()
    assert h.table.get(**EXECUTION_KEY)['status'] == status


@pytest.mark.parametrize('identifier', [{}, {'task_arn': TASK_ARN}], ids=['no identifier', 'legacy ECS task_arn'])
def test_execution_without_microvm_does_not_touch_the_running_record(identifier):
    _, h = _run([_record(**identifier)])
    h.dynamodb_client.delete_item.assert_not_called()


def test_missing_execution_is_404():
    response, h = _run([])

    assert response['statusCode'] == 404
    assert h.calls == []
