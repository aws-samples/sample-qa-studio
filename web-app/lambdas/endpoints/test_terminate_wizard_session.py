"""terminate_wizard_session Lambda: ends the wizard worker *and* its MicroVM.

Order: the execution record is made terminal first (``status = success``,
``wizard_status = closed``, ``completed_at``; conditional on ``pending`` /
``running`` — an already terminal record only gets ``wizard_status`` /
``completed_at``), then the terminate command on the wizard command channel
(EventBridge, SQS fallback), then — when the execution record carries
``microvm_id`` — ``TerminateMicrovm`` (best-effort), the VM's
start/termination time is recorded on the execution record (``GetMicrovm``;
``microvm_terminated_at`` is *now* while the VM winds down) and the
``RUNNING_EXECUTIONS`` tracking record is cleared.  The status is written
first because ``TerminateMicrovm`` SIGTERMs the worker within seconds and it
may never poll the command.  Sessions started before the MicroVM switch (no
``microvm_id``) never touch the MicroVM client.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from authz_test_support import EXEC_ID, UC_ID, make_event, resource_access_granted
import terminate_wizard_session
from terminate_wizard_session import handler

SESSION_ID = EXEC_ID
MICROVM_ID = 'vm-wizard-1'
EXECUTION_KEY = {'pk': {'S': f'USECASE_EXECUTION#{UC_ID}'}, 'sk': {'S': f'EXECUTION#{SESSION_ID}'}}
VM_STARTED = datetime(2026, 11, 5, 8, 0, 3, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env_and_access(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 'test-table')
    monkeypatch.setenv('WIZARD_EVENT_BUS_NAME', 'wizard-bus')
    monkeypatch.setenv('WIZARD_QUEUE_URL', 'https://sqs/wizard')
    with resource_access_granted():
        yield


def _event():
    return make_event('editor_a', path={'sessionId': SESSION_ID, 'usecaseId': UC_ID})


class _Harness:
    def __init__(self, execution_item):
        self.calls = []
        self.dynamodb = MagicMock(name='dynamodb')
        self.sqs = MagicMock(name='sqs')
        self.eventbridge = MagicMock(name='eventbridge')
        self.microvms = MagicMock(name='lambda-microvms')
        self.boto3 = MagicMock(name='boto3')
        self.boto3.client.side_effect = lambda service, **_: {'lambda-microvms': self.microvms}[service]

        self.dynamodb.get_item.return_value = {'Item': execution_item} if execution_item is not None else {}
        self.dynamodb.update_item.side_effect = self._update_item
        self.dynamodb.delete_item.side_effect = lambda **kw: self.calls.append(('delete_item', kw['Key'])) or {}
        self.eventbridge.put_events.side_effect = lambda **kw: self.calls.append(('put_events',)) or {}
        self.microvms.terminate_microvm.side_effect = (
            lambda **kw: self.calls.append(('terminate_microvm', kw['microvmIdentifier'])) or {})
        # Right after TerminateMicrovm the VM is still RUNNING: no terminatedAt yet.
        self.microvms.get_microvm.side_effect = (
            lambda **kw: self.calls.append(('get_microvm', kw['microvmIdentifier'])) or {
                'microvmId': kw['microvmIdentifier'], 'state': 'RUNNING', 'startedAt': VM_STARTED})

    def _update_item(self, **kw):
        name = 'record_runtime' if 'microvm_started_at' in kw['UpdateExpression'] else 'update_item'
        self.calls.append((name,))
        return {}

    def run(self):
        with patch('terminate_wizard_session.dynamodb', self.dynamodb), \
                patch('terminate_wizard_session.sqs', self.sqs), \
                patch('terminate_wizard_session.eventbridge', self.eventbridge), \
                patch('terminate_wizard_session.boto3', self.boto3):
            return handler(_event(), None)

    def microvm_client_requests(self):
        return [c for c in self.boto3.client.call_args_list if c.args[0] == 'lambda-microvms']

    def runtime_write(self):
        """kwargs of the ``microvm_started_at`` / ``microvm_terminated_at`` write, or None."""
        for call in self.dynamodb.update_item.call_args_list:
            if 'microvm_started_at' in call.kwargs['UpdateExpression']:
                return call.kwargs
        return None


def _record(**extra):
    return {**EXECUTION_KEY, 'status': {'S': 'running'}, 'mode': {'S': 'wizard'}, **extra}


class _Boto(BotoCoreError):
    fmt = 'endpoint down'


def test_lambda_init_is_the_first_import():
    source = open(terminate_wizard_session.__file__, encoding='utf-8').read()
    first_import = next(line for line in source.splitlines() if line.startswith(('import ', 'from ')))
    assert first_import.startswith('import lambda_init')


def test_microvm_session_is_closed_commanded_terminated_and_untracked():
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    response = h.run()

    assert response['statusCode'] == 200, response['body']
    assert json.loads(response['body']) == {'status': 'terminated', 'microvmId': MICROVM_ID}
    assert h.calls == [
        ('update_item',),
        ('put_events',),
        ('terminate_microvm', MICROVM_ID),
        ('get_microvm', MICROVM_ID),
        ('record_runtime',),
        ('delete_item', {'pk': {'S': 'RUNNING_EXECUTIONS'}, 'sk': {'S': f'EXECUTION#{SESSION_ID}'}}),
    ]
    h.dynamodb.get_item.assert_called_once_with(TableName='test-table', Key=EXECUTION_KEY)
    h.microvms.terminate_microvm.assert_called_once_with(microvmIdentifier=MICROVM_ID)
    assert len(h.microvm_client_requests()) == 1  # one client for TerminateMicrovm and GetMicrovm
    h.sqs.send_message.assert_not_called()


def test_microvm_runtime_is_recorded_on_the_session_record():
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.run()

    h.microvms.get_microvm.assert_called_once_with(microvmIdentifier=MICROVM_ID)
    write = h.runtime_write()
    assert write['TableName'] == 'test-table'
    assert write['Key'] == EXECUTION_KEY
    assert write['UpdateExpression'] == 'SET microvm_started_at = :started_at, microvm_terminated_at = :terminated_at'
    vals = write['ExpressionAttributeValues']
    assert vals[':started_at'] == {'S': '2026-11-05T08:00:03Z'}
    assert vals[':terminated_at']['S'] >= _status_writes(h)[0]['ExpressionAttributeValues'][':now']['S']


def test_self_terminated_vm_records_its_own_terminated_at():
    """A session the worker already ended (``timeout``): the VM is TERMINATED with exact timestamps."""
    h = _Harness(_record(status={'S': 'timeout'}, microvm_id={'S': MICROVM_ID}))
    h.microvms.get_microvm.side_effect = None
    h.microvms.get_microvm.return_value = {
        'state': 'TERMINATED', 'startedAt': VM_STARTED,
        'terminatedAt': datetime(2026, 11, 5, 8, 42, 0, tzinfo=timezone.utc)}
    response = h.run()
    assert response['statusCode'] == 200
    assert h.runtime_write()['ExpressionAttributeValues'][':terminated_at'] == {'S': '2026-11-05T08:42:00Z'}


@pytest.mark.parametrize('error', [
    ClientError({'Error': {'Code': 'ResourceNotFoundException', 'Message': 'gone'}}, 'GetMicrovm'),
    ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'GetMicrovm'),
    _Boto(),
])
def test_get_microvm_error_writes_no_runtime_and_the_session_is_still_untracked(error):
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.microvms.get_microvm.side_effect = error
    response = h.run()

    assert response['statusCode'] == 200
    assert json.loads(response['body']) == {'status': 'terminated', 'microvmId': MICROVM_ID}
    assert h.runtime_write() is None
    h.dynamodb.delete_item.assert_called_once()


def test_terminate_command_detail_is_unchanged():
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.run()
    entry = h.eventbridge.put_events.call_args.kwargs['Entries'][0]
    assert entry['Source'] == 'wizard.commands'
    assert entry['DetailType'] == 'WizardCommand'
    assert entry['EventBusName'] == 'wizard-bus'
    assert json.loads(entry['Detail']) == {'action': 'terminate', 'sessionId': SESSION_ID}


def test_session_without_microvm_id_skips_the_microvm_client_and_the_tracking_record():
    h = _Harness(_record())
    response = h.run()

    assert response['statusCode'] == 200
    assert json.loads(response['body']) == {'status': 'terminated'}
    assert h.microvm_client_requests() == []
    h.microvms.terminate_microvm.assert_not_called()
    h.dynamodb.delete_item.assert_not_called()


def test_missing_execution_record_still_sends_the_command():
    h = _Harness(None)
    response = h.run()
    assert response['statusCode'] == 200
    assert json.loads(response['body']) == {'status': 'terminated'}
    h.microvms.terminate_microvm.assert_not_called()


@pytest.mark.parametrize('error', [
    ClientError({'Error': {'Code': 'ResourceNotFoundException', 'Message': 'gone'}}, 'TerminateMicrovm'),
    _Boto(),
])
def test_terminate_error_is_tolerated_and_the_tracking_record_is_still_cleared(error):
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.microvms.terminate_microvm.side_effect = error
    response = h.run()

    assert response['statusCode'] == 200
    assert json.loads(response['body']) == {'status': 'terminated', 'microvmId': MICROVM_ID}
    h.dynamodb.delete_item.assert_called_once()


def test_execution_read_failure_is_tolerated():
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.dynamodb.get_item.side_effect = ClientError({'Error': {'Code': 'InternalServerError', 'Message': 'x'}}, 'GetItem')
    response = h.run()

    assert response['statusCode'] == 200
    assert json.loads(response['body']) == {'status': 'terminated'}
    h.microvms.terminate_microvm.assert_not_called()


def test_tracking_record_clear_failure_does_not_fail_the_request():
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.dynamodb.delete_item.side_effect = ClientError({'Error': {'Code': 'InternalServerError', 'Message': 'x'}}, 'DeleteItem')
    response = h.run()
    assert response['statusCode'] == 200
    assert json.loads(response['body'])['microvmId'] == MICROVM_ID


def test_command_send_failure_is_500_and_the_vm_is_left_alone():
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.eventbridge.put_events.side_effect = ClientError({'Error': {'Code': 'InternalException', 'Message': 'x'}}, 'PutEvents')
    response = h.run()

    assert response['statusCode'] == 500
    h.microvms.terminate_microvm.assert_not_called()
    h.dynamodb.delete_item.assert_not_called()


def test_sqs_fallback_without_event_bus(monkeypatch):
    monkeypatch.delenv('WIZARD_EVENT_BUS_NAME')
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    response = h.run()

    assert response['statusCode'] == 200
    h.sqs.send_message.assert_called_once()
    assert json.loads(h.sqs.send_message.call_args.kwargs['MessageBody']) == {'action': 'terminate', 'sessionId': SESSION_ID}
    h.eventbridge.put_events.assert_not_called()
    h.microvms.terminate_microvm.assert_called_once_with(microvmIdentifier=MICROVM_ID)


# ── the status write happens BEFORE the command / TerminateMicrovm ──────────

def _conditional_failed():
    return ClientError({'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'no'}}, 'UpdateItem')


def _status_writes(h):
    """The execution-record status writes (the VM runtime write is a separate, later update)."""
    return [c.kwargs for c in h.dynamodb.update_item.call_args_list
            if 'microvm_started_at' not in c.kwargs['UpdateExpression']]


def _runtime_writes(h):
    return [c.kwargs for c in h.dynamodb.update_item.call_args_list
            if 'microvm_started_at' in c.kwargs['UpdateExpression']]


def test_running_session_is_written_success_and_closed_before_the_command():
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.run()

    writes = _status_writes(h)
    assert len(writes) == 1
    write = writes[0]
    assert write['TableName'] == 'test-table'
    assert write['Key'] == EXECUTION_KEY
    assert write['UpdateExpression'] == (
        'SET #status = :success, wizard_status = :closed, completed_at = :now')
    assert write['ExpressionAttributeNames'] == {'#status': 'status'}
    assert write['ConditionExpression'] == '#status IN (:pending, :running)'
    vals = write['ExpressionAttributeValues']
    assert vals[':success'] == {'S': 'success'}
    assert vals[':closed'] == {'S': 'closed'}
    assert vals[':pending'] == {'S': 'pending'}
    assert vals[':running'] == {'S': 'running'}
    assert vals[':now']['S']
    # status before the command, the command before the VM
    assert h.calls[:3] == [('update_item',), ('put_events',), ('terminate_microvm', MICROVM_ID)]


def test_already_terminal_session_falls_back_to_the_wizard_status_only_update():
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    outcomes = iter([_conditional_failed(), {}])

    def update_item(**kw):
        if 'microvm_started_at' in kw['UpdateExpression']:
            return h._update_item(**kw)
        h.calls.append(('update_item',))
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    h.dynamodb.update_item.side_effect = update_item
    response = h.run()

    assert response['statusCode'] == 200
    writes = _status_writes(h)
    assert len(writes) == 2
    assert 'ConditionExpression' in writes[0]
    fallback = writes[1]
    assert fallback['Key'] == EXECUTION_KEY
    assert fallback['UpdateExpression'] == 'SET wizard_status = :status, completed_at = :completed'
    assert 'ConditionExpression' not in fallback
    assert fallback['ExpressionAttributeValues'][':status'] == {'S': 'closed'}
    assert '#status' not in fallback['UpdateExpression']  # the terminal status is kept
    # the rest of the flow still runs
    assert h.calls[2:] == [
        ('put_events',),
        ('terminate_microvm', MICROVM_ID),
        ('get_microvm', MICROVM_ID),
        ('record_runtime',),
        ('delete_item', {'pk': {'S': 'RUNNING_EXECUTIONS'}, 'sk': {'S': f'EXECUTION#{SESSION_ID}'}}),
    ]


def test_other_status_write_errors_are_logged_and_the_flow_continues(capsys):
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.dynamodb.update_item.side_effect = ClientError(
        {'Error': {'Code': 'InternalServerError', 'Message': 'x'}}, 'UpdateItem')
    response = h.run()

    assert response['statusCode'] == 200
    assert len(_status_writes(h)) == 1  # no fallback for a non-conditional error
    assert len(_runtime_writes(h)) == 1  # attempted (and failed, best-effort) like the rest of the flow
    h.eventbridge.put_events.assert_called_once()
    h.microvms.terminate_microvm.assert_called_once_with(microvmIdentifier=MICROVM_ID)
    assert 'Error updating execution status' in capsys.readouterr().out


def test_fallback_write_error_is_logged_and_the_flow_continues(capsys):
    h = _Harness(_record(microvm_id={'S': MICROVM_ID}))
    h.dynamodb.update_item.side_effect = [
        _conditional_failed(),
        ClientError({'Error': {'Code': 'InternalServerError', 'Message': 'x'}}, 'UpdateItem'),
        {},  # the VM runtime write
    ]
    response = h.run()

    assert response['statusCode'] == 200
    assert len(_status_writes(h)) == 2
    assert len(_runtime_writes(h)) == 1
    h.eventbridge.put_events.assert_called_once()
    assert 'Error updating execution status' in capsys.readouterr().out
