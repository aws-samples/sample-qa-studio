"""What ``execute_usecase`` still does for step caching (trajectory replay).

The bbox step cache was removed (codebase-health B5); what remains:

- ``enable_cache`` on the use case is copied to the execution record.
- The step runtime fields (``trajectory_s3_key`` / ``trajectory_last_updated``
  and, for one release, the legacy ``cached_steps`` / ``cache_last_updated``)
  are copied STEP# → EXECUTION_STEP# so the runner can replay.
- The worker no longer gets ``CACHE_ACTION_DELAY_MS`` (the RunPayload carries
  no cache settings).
"""
import json
import os

import pytest
from unittest.mock import MagicMock, patch

from execute_usecase import handler
from run_payload import RunPayload

EXECUTOR_TEAM_A = json.dumps([{'team_id': 'team-a', 'role': 'executor'}])

_MICROVM_ENV = {
    'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1', 'S3_BUCKET_PREFIX': 'bucket',
    'AWS_REGION': 'us-east-1',
    'MICROVM_IMAGE_ARN': 'arn:aws:lambda:us-east-1:1:microvm-image:w', 'MICROVM_IMAGE_VERSION': '1.0',
    'MICROVM_EXECUTION_ROLE_ARN': 'arn:aws:iam::1:role/exec', 'MICROVM_LOG_GROUP': '/qa-studio/test/microvm',
    'MAX_EXECUTION_DURATION_MINUTES': '60',
}


@pytest.fixture(autouse=True)
def _owned_usecase():
    with patch('resource_auth.get_usecase_owner',
               return_value={'application_id': 'app-1', 'owner_team_id': 'team-a', 'created_by': None}):
        yield


@pytest.fixture
def microvm_env(monkeypatch):
    for key, value in _MICROVM_ENV.items():
        monkeypatch.setenv(key, value)


def _event(trigger_type):
    return {
        'pathParameters': {'id': 'usecase123'},
        'queryStringParameters': {'trigger-type': trigger_type},
        'requestContext': {'authorizer': {'claims': {
            'email': 'test@example.com', 'scope': 'api/usecases.execute', 'teamRoles': EXECUTOR_TEAM_A,
        }}},
    }


def _usecase(**extra):
    return {'Item': {
        'starting_url': {'S': 'https://example.com'},
        'executing_region': {'S': 'us-east-1'},
        'model_id': {'S': 'nova-act-v1'},
        **extra,
    }}


def _execution_step_items(mock_dynamodb):
    """EXECUTION_STEP# items persisted through ``batch_write_item``."""
    return [
        request['PutRequest']['Item']
        for c in mock_dynamodb.batch_write_item.call_args_list
        for requests in c.kwargs['RequestItems'].values()
        for request in requests
        if request['PutRequest']['Item']['pk']['S'].startswith('EXECUTION#')
        and request['PutRequest']['Item']['sk']['S'].startswith('EXECUTION_STEP#')
    ]


def _run(event, usecase, steps):
    microvms = MagicMock()
    microvms.meta.region_name = 'us-east-1'
    microvms.run_microvm.return_value = {'microvmId': 'vm-1', 'state': 'PENDING'}
    with patch('execute_usecase.dynamodb') as mock_dynamodb, \
            patch('microvm_launch.get_microvm_client', return_value=microvms), \
            patch('execute_usecase.eventbridge'), \
            patch('execute_usecase.allow_m2m_token',
                  return_value=({'identity': 'test@example.com', 'identity_type': 'user'}, None)), \
            patch('execute_usecase.get_table_name', return_value='test-table'), \
            patch('execute_usecase.get_current_timestamp', return_value='2026-03-03T12:00:00Z'):
        mock_dynamodb.get_item.side_effect = [usecase]
        mock_dynamodb.query.return_value = {'Items': steps}
        response = handler(event, None)
    return response, mock_dynamodb, microvms


class TestEnableCachePropagation:
    @pytest.mark.parametrize('flag,expected', [(True, {'BOOL': True}), (False, None)])
    def test_enable_cache_copied_to_execution_record(self, flag, expected):
        usecase = _usecase(enable_cache={'BOOL': flag})
        response, ddb, _ = _run(_event('ci_runner'), usecase, [])

        assert response['statusCode'] == 200
        execution = ddb.put_item.call_args_list[0].kwargs['Item']
        assert execution.get('enable_cache') == expected


class TestRuntimeFieldsCopiedToExecutionSteps:
    def test_trajectory_and_legacy_fields_copied_when_present(self):
        steps = [
            {
                'id': {'S': 'step1'}, 'sort': {'N': '0'}, 'instruction': {'S': 'Click login'},
                'step_type': {'S': 'navigation'},
                'trajectory_s3_key': {'S': 'trajectories/usecase123/step1.json'},
                'trajectory_last_updated': {'S': '2026-03-03T10:00:00Z'},
                'cached_steps': {'S': '[{"type":"click"}]'},
                'cache_last_updated': {'S': '2026-03-01T10:00:00Z'},
            },
            {'id': {'S': 'step2'}, 'sort': {'N': '1'}, 'instruction': {'S': 'Verify title'},
             'step_type': {'S': 'validation'}},
        ]
        response, ddb, _ = _run(_event('ci_runner'), _usecase(), steps)

        assert response['statusCode'] == 200
        first, second = _execution_step_items(ddb)
        assert first['trajectory_s3_key']['S'] == 'trajectories/usecase123/step1.json'
        assert first['trajectory_last_updated']['S'] == '2026-03-03T10:00:00Z'
        assert first['cached_steps']['S'] == '[{"type":"click"}]'
        for field in ('trajectory_s3_key', 'trajectory_last_updated', 'cached_steps', 'cache_last_updated'):
            assert field not in second


class TestWorkerPayload:
    def test_no_cache_action_delay_for_headless_runs(self, microvm_env):
        response, _, microvms = _run(_event('OnDemandHeadless'), _usecase(), [])

        assert response['statusCode'] == 200, response['body']
        raw = microvms.run_microvm.call_args.kwargs['runHookPayload']
        assert 'CACHE_ACTION_DELAY_MS' not in raw and 'cache_action_delay' not in raw
        payload = RunPayload.from_hook_payload(raw)
        assert payload.usecase_id == 'usecase123'
        assert payload.execution_id
