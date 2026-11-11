"""``microvm_launch``: the shared ``RunMicrovm`` call used by the launch Lambdas."""
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

import microvm_launch
from microvm_launch import (
    MIN_IDLE_DURATION_S,
    RUN_MICROVM_ATTEMPTS,
    get_microvm_client,
    launch_microvm,
    microvm_cloudwatch_logs_url,
    no_ingress_connector_arn,
)
from run_payload import RunPayload

IMAGE_ARN = 'arn:aws:lambda:eu-central-1:123456789012:microvm-image:test-worker'
EXEC_ROLE = 'arn:aws:iam::123456789012:role/test-microvm-execution-role'
LOG_GROUP = '/qa-studio/test/microvm'


def _payload(**overrides):
    fields = dict(
        mode='batch', usecase_id='uc-1', execution_id='ex-1', execution_token='tok-1',
        region='us-east-1', s3_bucket='b-us-east-1', max_duration_s=3600,
    )
    fields.update(overrides)
    return RunPayload(**fields)


def _client(region='eu-central-1'):
    client = MagicMock()
    client.meta.region_name = region
    client.run_microvm.return_value = {'microvmId': 'vm-1', 'state': 'PENDING'}
    return client


def _throttle():
    return ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'slow down'}}, 'RunMicrovm')


def _launch(client, **overrides):
    kwargs = dict(
        image_arn=IMAGE_ARN, image_version='1.0', execution_role_arn=EXEC_ROLE,
        log_group=LOG_GROUP, log_stream='ex-1', payload=_payload(), max_duration_s=3600,
    )
    kwargs.update(overrides)
    return launch_microvm(client, **kwargs)


class TestLaunchMicrovm:
    def test_calls_run_microvm_with_the_documented_parameters(self):
        client = _client()
        result = _launch(client)

        assert result == {'microvmId': 'vm-1', 'state': 'PENDING'}
        client.run_microvm.assert_called_once()
        kwargs = client.run_microvm.call_args.kwargs
        assert kwargs['imageIdentifier'] == IMAGE_ARN
        assert kwargs['imageVersion'] == '1.0'
        assert kwargs['executionRoleArn'] == EXEC_ROLE
        assert kwargs['ingressNetworkConnectors'] == [
            'arn:aws:lambda:eu-central-1:aws:network-connector:aws-network-connector:NO_INGRESS'
        ]
        # Egress defaults to INTERNET_EGRESS; explicit ARNs are rejected (spike).
        assert 'egressNetworkConnectors' not in kwargs
        assert kwargs['idlePolicy'] == {
            'maxIdleDurationSeconds': 3600, 'suspendedDurationSeconds': 0, 'autoResumeEnabled': False,
        }
        assert kwargs['logging'] == {'cloudWatch': {'logGroup': LOG_GROUP, 'logStream': 'ex-1'}}
        assert kwargs['maximumDurationInSeconds'] == 3600
        assert 'clientToken' not in kwargs
        parsed = RunPayload.from_hook_payload(kwargs['runHookPayload'])
        assert parsed == _payload()
        assert parsed.execution_token.get_secret_value() == 'tok-1'

    def test_connector_region_follows_the_client_region(self):
        client = _client(region='us-east-1')
        _launch(client)
        assert client.run_microvm.call_args.kwargs['ingressNetworkConnectors'] == [
            'arn:aws:lambda:us-east-1:aws:network-connector:aws-network-connector:NO_INGRESS'
        ]

    def test_client_token_is_passed_through_when_given(self):
        client = _client()
        _launch(client, client_token='ex-1')
        assert client.run_microvm.call_args.kwargs['clientToken'] == 'ex-1'

    def test_idle_duration_is_clamped_to_the_platform_minimum(self):
        client = _client()
        _launch(client, max_duration_s=30, payload=_payload(max_duration_s=30))
        kwargs = client.run_microvm.call_args.kwargs
        assert MIN_IDLE_DURATION_S == 60
        assert kwargs['idlePolicy']['maxIdleDurationSeconds'] == 60
        assert kwargs['maximumDurationInSeconds'] == 30

    def test_throttling_is_retried_then_succeeds(self):
        client = _client()
        client.run_microvm.side_effect = [_throttle()] * (RUN_MICROVM_ATTEMPTS - 1) + [{'microvmId': 'vm-2'}]
        with patch('microvm_launch.time.sleep') as sleep:
            result = _launch(client)
        assert RUN_MICROVM_ATTEMPTS == 5
        assert result == {'microvmId': 'vm-2'}
        assert client.run_microvm.call_count == 5
        waits = [c.args[0] for c in sleep.call_args_list]
        assert len(waits) == 4
        assert waits == sorted(waits) and waits[0] < waits[-1]  # exponential backoff

    def test_throttling_on_every_attempt_reraises(self):
        client = _client()
        client.run_microvm.side_effect = _throttle()
        with patch('microvm_launch.time.sleep') as sleep, pytest.raises(ClientError) as exc:
            _launch(client)
        assert exc.value.response['Error']['Code'] == 'ThrottlingException'
        assert client.run_microvm.call_count == RUN_MICROVM_ATTEMPTS
        assert sleep.call_count == RUN_MICROVM_ATTEMPTS - 1

    def test_other_client_errors_are_not_retried(self):
        client = _client()
        client.run_microvm.side_effect = ClientError(
            {'Error': {'Code': 'ValidationException', 'Message': 'bad'}}, 'RunMicrovm')
        with patch('microvm_launch.time.sleep') as sleep, pytest.raises(ClientError):
            _launch(client)
        assert client.run_microvm.call_count == 1
        sleep.assert_not_called()

    def test_oversized_payload_raises_before_any_call(self):
        from run_payload import PayloadTooLargeError
        client = _client()
        with pytest.raises(PayloadTooLargeError):
            _launch(client, payload=_payload(user_agent='x' * 5000))
        client.run_microvm.assert_not_called()


class TestHelpers:
    def test_no_ingress_connector_arn(self):
        assert no_ingress_connector_arn('eu-central-1') == (
            'arn:aws:lambda:eu-central-1:aws:network-connector:aws-network-connector:NO_INGRESS'
        )

    def test_cloudwatch_logs_url_deep_links_to_the_execution_stream(self):
        # Same format as execute_usecase.generate_cloudwatch_logs_url (urllib quote, '/' kept).
        url = microvm_cloudwatch_logs_url('eu-central-1', '/qa-studio/test/microvm', 'ex-1')
        assert url == (
            'https://eu-central-1.console.aws.amazon.com/cloudwatch/home?region=eu-central-1'
            '#logsV2:log-groups/log-group//qa-studio/test/microvm/log-events/ex-1'
        )

    def test_client_is_created_lazily_and_cached(self):
        microvm_launch._client = None
        with patch('microvm_launch.boto3.client') as make_client:
            make_client.return_value = 'client'
            assert get_microvm_client() == 'client'
            assert get_microvm_client() == 'client'
        make_client.assert_called_once_with('lambda-microvms')
        microvm_launch._client = None

    def test_module_import_does_not_construct_the_client(self):
        # Older botocore (test envs) has no lambda-microvms model; the ecs path must never need it.
        import importlib
        with patch('boto3.client') as make_client:
            reloaded = importlib.reload(microvm_launch)
        make_client.assert_not_called()
        assert reloaded._client is None
