"""start_wizard_session Lambda: wizard sessions launch on a Lambda MicroVM (phase 2).

The handler creates the use-case and wizard execution records as before, then
calls ``microvm_launch.launch_microvm`` with a ``mode='wizard'`` RunPayload
instead of ``ecs.run_task``.  The execution record gets ``microvm_id`` and
``cloudwatch_logs_url`` (no ECS task fields), the ``RUNNING_EXECUTIONS``
tracking record is written with ``mode='wizard'`` (best-effort), and a launch
failure marks the session ``failed`` and returns 500.
"""
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from authz_test_support import APP_ID, make_event, resource_access_granted
from run_payload import RunPayload
import start_wizard_session
from start_wizard_session import handler

ENV = {
    'TABLE_NAME': 'test-table',
    'S3_BUCKET_PREFIX': '123-studio-artefacts',
    'DEFAULT_REGION': 'eu-central-1',
    'AWS_REGION': 'eu-central-1',
    'MICROVM_IMAGE_ARN': 'arn:aws:lambda:eu-central-1:123456789012:microvm-image:test-worker',
    'MICROVM_IMAGE_VERSION': '3.0',
    'MICROVM_EXECUTION_ROLE_ARN': 'arn:aws:iam::123456789012:role/test-microvm-execution-role',
    'MICROVM_LOG_GROUP': '/qa-studio/test/microvm',
    'MAX_WIZARD_SESSION_MINUTES': '90',
}

BODY = {'application_id': APP_ID, 'name': 'wizard', 'starting_url': 'https://example.test'}


@pytest.fixture(autouse=True)
def _env_and_access(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    with resource_access_granted():
        yield


def _event(**body):
    return make_event('editor_a', body={**BODY, **body})


def _run(dynamodb=None, run_microvm=None, event=None):
    """Invoke the handler with a mocked DynamoDB client and MicroVM client."""
    dynamodb = dynamodb if dynamodb is not None else MagicMock(name='dynamodb')
    client = MagicMock(name='lambda-microvms')
    client.meta.region_name = 'eu-central-1'
    if run_microvm is not None:
        client.run_microvm.side_effect = run_microvm
    else:
        client.run_microvm.return_value = {'microvmId': 'vm-wizard-1', 'state': 'PENDING'}
    with patch('start_wizard_session.dynamodb', dynamodb), \
            patch('microvm_launch.get_microvm_client', return_value=client), \
            patch('microvm_launch.time.sleep'):
        response = handler(event or _event(), None)
    return response, dynamodb, client


def _put_items(dynamodb):
    return [c.kwargs['Item'] for c in dynamodb.put_item.call_args_list]


def _execution_item(dynamodb):
    return next(i for i in _put_items(dynamodb) if i['pk']['S'].startswith('USECASE_EXECUTION#'))


def _running_item(dynamodb):
    return next((i for i in _put_items(dynamodb) if i['pk']['S'] == 'RUNNING_EXECUTIONS'), None)


def _updates(dynamodb):
    return [c.kwargs for c in dynamodb.update_item.call_args_list]


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def test_no_ecs_client_and_no_ecs_env_reads():
    assert not hasattr(start_wizard_session, 'ecs')
    source = open(start_wizard_session.__file__, encoding='utf-8').read()
    for name in ('ECS_CLUSTER', 'ECS_TASK_DEFINITION', 'SUBNET_ID', 'SECURITY_GROUP_ID', 'run_task'):
        assert name not in source, name


def test_lambda_init_is_the_first_import():
    source = open(start_wizard_session.__file__, encoding='utf-8').read()
    first_import = next(line for line in source.splitlines() if line.startswith(('import ', 'from ')))
    assert first_import.startswith('import lambda_init')


def test_returns_201_with_session_usecase_and_microvm_ids():
    response, _dynamodb, client = _run()

    assert response['statusCode'] == 201, response['body']
    body = json.loads(response['body'])
    assert body['status'] == 'initializing'
    assert body['microvmId'] == 'vm-wizard-1'
    assert body['sessionId'] and body['usecaseId']
    client.run_microvm.assert_called_once()


def test_run_microvm_parameters_match_the_batch_launcher_settings():
    response, _dynamodb, client = _run()
    session_id = json.loads(response['body'])['sessionId']
    kwargs = client.run_microvm.call_args.kwargs

    assert kwargs['imageIdentifier'] == ENV['MICROVM_IMAGE_ARN']
    assert kwargs['imageVersion'] == '3.0'
    assert kwargs['executionRoleArn'] == ENV['MICROVM_EXECUTION_ROLE_ARN']
    assert kwargs['ingressNetworkConnectors'] == [
        'arn:aws:lambda:eu-central-1:aws:network-connector:aws-network-connector:NO_INGRESS']
    assert 'egressNetworkConnectors' not in kwargs
    assert kwargs['maximumDurationInSeconds'] == 90 * 60
    assert kwargs['idlePolicy'] == {
        'maxIdleDurationSeconds': 90 * 60, 'suspendedDurationSeconds': 0, 'autoResumeEnabled': False}
    assert kwargs['logging'] == {'cloudWatch': {'logGroup': '/qa-studio/test/microvm', 'logStream': session_id}}
    assert kwargs['clientToken'] == session_id


def test_payload_is_wizard_mode_with_session_and_regional_bucket():
    response, _dynamodb, client = _run(event=_event(executing_region='us-east-1'))
    body = json.loads(response['body'])
    payload = RunPayload.from_hook_payload(client.run_microvm.call_args.kwargs['runHookPayload'])

    assert payload.mode == 'wizard'
    assert payload.session_id == body['sessionId']
    assert payload.usecase_id == body['usecaseId']
    assert payload.execution_id is None
    assert payload.execution_token is None
    assert payload.region == 'us-east-1'
    assert payload.s3_bucket == '123-studio-artefacts-us-east-1'
    assert payload.max_duration_s == 90 * 60
    assert payload.mobile is None


def test_default_region_selects_the_default_bucket():
    _response, _dynamodb, client = _run()
    payload = RunPayload.from_hook_payload(client.run_microvm.call_args.kwargs['runHookPayload'])
    assert (payload.region, payload.s3_bucket) == ('eu-central-1', '123-studio-artefacts-eu-central-1')


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def test_execution_record_gets_microvm_id_and_logs_url_but_no_task_fields():
    response, dynamodb, _client = _run()
    body = json.loads(response['body'])
    execution = _execution_item(dynamodb)
    assert execution['sk'] == {'S': f"EXECUTION#{body['sessionId']}"}
    assert execution['mode'] == {'S': 'wizard'}

    updates = _updates(dynamodb)
    assert len(updates) == 1
    update = updates[0]
    assert update['Key'] == {'pk': {'S': f"USECASE_EXECUTION#{body['usecaseId']}"},
                             'sk': {'S': f"EXECUTION#{body['sessionId']}"}}
    assert 'microvm_id' in update['UpdateExpression']
    assert 'cloudwatch_logs_url' in update['UpdateExpression']
    assert 'task_arn' not in update['UpdateExpression']
    assert update['ExpressionAttributeValues'][':microvm_id'] == {'S': 'vm-wizard-1'}
    assert update['ExpressionAttributeValues'][':cloudwatch_url'] == {'S': (
        'https://eu-central-1.console.aws.amazon.com/cloudwatch/home?region=eu-central-1'
        f"#logsV2:log-groups/log-group//qa-studio/test/microvm/log-events/{body['sessionId']}")}


def test_running_executions_record_is_written_with_wizard_mode():
    response, dynamodb, _client = _run()
    body = json.loads(response['body'])
    item = _running_item(dynamodb)

    assert item is not None
    assert item['sk'] == {'S': f"EXECUTION#{body['sessionId']}"}
    assert item['usecase_id'] == {'S': body['usecaseId']}
    assert item['microvm_id'] == {'S': 'vm-wizard-1'}
    assert item['mode'] == {'S': 'wizard'}
    assert 'suite_execution_id' not in item
    assert 'started_at' in item and 'deadline' in item
    # written AFTER the execution record got its microvm_id
    order = [c[0] for c in dynamodb.method_calls if c[0] in ('put_item', 'update_item')]
    assert order == ['put_item', 'put_item', 'update_item', 'put_item']


def test_running_record_failure_does_not_fail_the_launch():
    dynamodb = MagicMock(name='dynamodb')

    def put_item(**kwargs):
        if kwargs['Item']['pk']['S'] == 'RUNNING_EXECUTIONS':
            raise ClientError({'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'x'}}, 'PutItem')
        return {}

    dynamodb.put_item.side_effect = put_item
    response, _dynamodb, _client = _run(dynamodb=dynamodb)
    assert response['statusCode'] == 201, response['body']
    assert json.loads(response['body'])['microvmId'] == 'vm-wizard-1'


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------

class _Boto(BotoCoreError):
    fmt = 'endpoint down'


@pytest.mark.parametrize('error', [
    ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'RunMicrovm'),
    _Boto(),
])
def test_launch_failure_marks_the_session_failed_and_returns_500(error):
    response, dynamodb, client = _run(run_microvm=error)

    assert response['statusCode'] == 500
    assert 'Failed to start MicroVM' in json.loads(response['body'])['error']
    client.run_microvm.assert_called_once()
    execution = _execution_item(dynamodb)
    updates = _updates(dynamodb)
    assert len(updates) == 1
    update = updates[0]
    assert update['Key'] == {'pk': execution['pk'], 'sk': execution['sk']}
    assert update['ExpressionAttributeNames'] == {'#status': 'status'}
    assert update['ExpressionAttributeValues'][':status'] == {'S': 'failed'}
    assert update['ExpressionAttributeValues'][':wizard_status'] == {'S': 'closed'}
    assert 'Failed to start MicroVM' in update['ExpressionAttributeValues'][':error_msg']['S']
    assert ':completed_at' in update['ExpressionAttributeValues']
    assert _running_item(dynamodb) is None


def test_throttling_is_retried_then_succeeds():
    throttled = ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'slow'}}, 'RunMicrovm')
    response, _dynamodb, client = _run(run_microvm=[throttled, throttled, {'microvmId': 'vm-late'}])
    assert response['statusCode'] == 201
    assert json.loads(response['body'])['microvmId'] == 'vm-late'
    assert client.run_microvm.call_count == 3


def test_missing_name_is_400_before_any_write():
    response, dynamodb, client = _run(event=make_event('editor_a', body={'application_id': APP_ID, 'name': '',
                                                                           'starting_url': 'https://x'}))
    assert response['statusCode'] == 400
    assert not dynamodb.put_item.called
    client.run_microvm.assert_not_called()


def test_invalid_region_is_400_before_any_write():
    response, dynamodb, client = _run(event=_event(executing_region='nowhere'))
    assert response['statusCode'] == 400
    assert not dynamodb.put_item.called
    client.run_microvm.assert_not_called()


def test_record_write_failure_is_500_without_a_launch():
    dynamodb = MagicMock(name='dynamodb')
    dynamodb.put_item.side_effect = ClientError({'Error': {'Code': 'InternalServerError', 'Message': 'x'}}, 'PutItem')
    response, _dynamodb, client = _run(dynamodb=dynamodb)
    assert response['statusCode'] == 500
    assert json.loads(response['body']) == {'error': 'Failed to start wizard session'}
    client.run_microvm.assert_not_called()
