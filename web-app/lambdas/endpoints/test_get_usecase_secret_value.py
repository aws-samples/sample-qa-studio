"""Unit tests for get_usecase_secret_value Lambda function (H-1)."""
import json
import logging
import os
from unittest.mock import patch, MagicMock

import pytest

from authz_test_support import (
    UC_ID, EXEC_ID, TEAM_B, make_event, owned_resources, share, worker_header, execution_record,
)
from get_usecase_secret_value import handler

SCOPES = 'api/usecases.read api/usecases.execute api/executions.read api/executions.write'


@pytest.fixture(autouse=True)
def _prefix(monkeypatch):
    monkeypatch.setenv('SECRET_PREFIX', 'test-prefix')


@pytest.fixture
def secrets_client():
    client = MagicMock()
    client.exceptions.ResourceNotFoundException = type('ResourceNotFoundException', (Exception,), {})
    client.get_secret_value.return_value = {'SecretString': 's3cret_v@lue'}
    with patch('get_usecase_secret_value.boto3') as mock_boto3:
        mock_boto3.client.return_value = client
        yield client


def _event(caller='executor_a', secret_key='my_password', scopes=SCOPES, usecase_id=UC_ID, **kwargs):
    return make_event(caller, path={'id': usecase_id, 'secret_key': secret_key}, scopes=scopes, **kwargs)


def _call(event, **owned):
    with owned_resources(**owned):
        return handler(event, None)


class TestSecretValueSuccess:
    def test_owner_executor_gets_value(self, secrets_client):
        response = _call(_event())
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body == {'key': 'my_password', 'value': 's3cret_v@lue'}
        secrets_client.get_secret_value.assert_called_once_with(
            SecretId=f'test-prefix/usecase/{UC_ID}/my_password')

    def test_secret_not_found_returns_404(self, secrets_client):
        secrets_client.get_secret_value.side_effect = secrets_client.exceptions.ResourceNotFoundException('x')
        response = _call(_event())
        assert response['statusCode'] == 404
        assert 'not found' in json.loads(response['body'])['error']

    def test_secret_with_no_value_returns_404(self, secrets_client):
        secrets_client.get_secret_value.return_value = {'SecretString': None}
        response = _call(_event())
        assert response['statusCode'] == 404
        assert 'no value' in json.loads(response['body'])['error']

    def test_secrets_manager_error_returns_500(self, secrets_client):
        secrets_client.get_secret_value.side_effect = RuntimeError('boom')
        response = _call(_event())
        assert response['statusCode'] == 500
        assert 'Failed to retrieve secret value' in json.loads(response['body'])['error']

    def test_access_is_logged_without_value(self, secrets_client, caplog):
        with caplog.at_level(logging.INFO):
            _call(_event())
        access = [r.getMessage() for r in caplog.records if 'secret_value_access' in r.getMessage()]
        assert len(access) == 1
        assert f'usecase={UC_ID}' in access[0] and 'key=my_password' in access[0]
        assert 'sub=caller-sub' in access[0]
        assert all('s3cret_v@lue' not in r.getMessage() for r in caplog.records)


class TestSecretValueAccess:
    def test_read_scope_alone_is_not_enough(self, secrets_client):
        response = _call(_event(scopes='api/usecases.read'))
        assert response['statusCode'] == 403
        secrets_client.get_secret_value.assert_not_called()

    def test_viewer_403(self, secrets_client):
        assert _call(_event('viewer_a'))['statusCode'] == 403
        secrets_client.get_secret_value.assert_not_called()

    def test_other_team_executor_403(self, secrets_client):
        assert _call(_event('executor_b'))['statusCode'] == 403
        secrets_client.get_secret_value.assert_not_called()

    def test_shared_view_403(self, secrets_client):
        assert _call(_event('executor_b'), shares=share('view'))['statusCode'] == 403

    def test_shared_execute_200(self, secrets_client):
        assert _call(_event('executor_b'), shares=share('execute'))['statusCode'] == 200

    def test_shared_execute_viewer_role_403(self, secrets_client):
        # ceiling rule: a viewer in the target team stays view-only
        assert _call(_event('viewer_b'), shares=share('full', target_team=TEAM_B))['statusCode'] == 403

    def test_unbound_client_403(self, secrets_client):
        assert _call(_event('client_unbound'))['statusCode'] == 403

    def test_bound_client_200(self, secrets_client):
        assert _call(_event('client_a'))['statusCode'] == 200

    def test_client_bound_to_other_team_403(self, secrets_client):
        assert _call(_event('client_b'))['statusCode'] == 403

    def test_orphan_usecase_admin_only(self, secrets_client):
        assert _call(_event('executor_a'), usecase_app='')['statusCode'] == 403
        assert _call(_event('admin'), usecase_app='')['statusCode'] == 200

    def test_unknown_usecase_404(self, secrets_client):
        assert _call(_event(usecase_id='uc-unknown'))['statusCode'] == 404


class TestSecretValueWorker:
    def test_worker_own_execution_200(self, secrets_client):
        assert _call(_event('worker', worker_header=worker_header()))['statusCode'] == 200

    def test_worker_token_for_other_usecase_403(self, secrets_client):
        # A valid token for an execution of uc-other can't read UC_ID's secrets.
        executions = {('uc-other', EXEC_ID): execution_record()}
        event = _event('worker', worker_header=worker_header(usecase_id='uc-other'))
        assert _call(event, executions=executions)['statusCode'] == 403
        secrets_client.get_secret_value.assert_not_called()

    @pytest.mark.parametrize('status', ['success', 'failed', 'stopped'])
    def test_worker_token_for_finished_execution_403(self, secrets_client, status):
        executions = {(UC_ID, EXEC_ID): execution_record(status=status)}
        event = _event('worker', worker_header=worker_header())
        assert _call(event, executions=executions)['statusCode'] == 403

    def test_worker_wrong_token_403(self, secrets_client):
        event = _event('worker', worker_header=worker_header(token='wrong'))
        assert _call(event)['statusCode'] == 403

    def test_worker_without_header_403(self, secrets_client):
        assert _call(_event('worker'))['statusCode'] == 403


class TestSecretKeyValidation:
    @pytest.mark.parametrize('key', ['../other/key', 'a/b', 'a b', 'k@y', 'x' * 129, 'é'])
    def test_malformed_key_400(self, secrets_client, key):
        response = _call(_event(secret_key=key))
        assert response['statusCode'] == 400
        assert 'Invalid secret key' in json.loads(response['body'])['error']
        secrets_client.get_secret_value.assert_not_called()

    @pytest.mark.parametrize('key', ['my_password', 'API.KEY-1', 'x' * 128])
    def test_valid_key_accepted(self, secrets_client, key):
        assert _call(_event(secret_key=key))['statusCode'] == 200

    def test_missing_secret_key_400(self, secrets_client):
        event = make_event('executor_a', path={'id': UC_ID}, scopes=SCOPES)
        response = _call(event)
        assert response['statusCode'] == 400
        assert 'Missing secret key' in json.loads(response['body'])['error']

    def test_missing_usecase_id_400(self, secrets_client):
        event = make_event('executor_a', path={'secret_key': 'k'}, scopes=SCOPES)
        response = _call(event)
        assert response['statusCode'] == 400
        assert 'usecase ID is required' in json.loads(response['body'])['error']
