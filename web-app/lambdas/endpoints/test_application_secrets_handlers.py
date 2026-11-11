"""
Tests for the application secrets handlers behind the application router:

- GET    /applications/{id}/secrets   (view,  api/applications.read)
- POST   /applications/{id}/secrets   (edit,  api/applications.write)
- DELETE /applications/{id}/secrets   (edit,  api/applications.write)

Secrets Manager is mocked; resource auth is driven through authz_test_support
(APP_ID is owned by TEAM_A).
"""
import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from authz_test_support import APP_ID, make_event, owned_resources, share
from handlers import delete_application_secrets, get_application_secrets, put_application_secrets

PREFIX = 'p'
APP_PREFIX = f'{PREFIX}/application/{APP_ID}/'
READ = 'api/applications.read'
WRITE = 'api/applications.write'


@pytest.fixture(autouse=True)
def secrets_client(monkeypatch):
    monkeypatch.setenv('SECRET_PREFIX', PREFIX)
    client = MagicMock()
    client.list_secrets.return_value = {'SecretList': [
        {'Name': f'{APP_PREFIX}admin_password', 'Description': 'd',
         'CreatedDate': datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)},
        {'Name': f'{PREFIX}/application/other-app/admin_password'},
    ]}
    with patch('boto3.client', return_value=client):
        yield client


def _client_error(code, operation='CreateSecret'):
    return ClientError({'Error': {'Code': code, 'Message': code}}, operation)


def _call(module, caller, body=None, scopes=None, app_id=APP_ID, **owned):
    default_scope = WRITE if module is not get_application_secrets else READ
    event = make_event(caller, path={'id': app_id}, body=body,
                       scopes=scopes if scopes is not None else default_scope)
    with owned_resources(**owned):
        return module.handle(event)


def _body(response):
    return json.loads(response['body'])


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


class TestGetApplicationSecrets:
    def test_lists_application_secrets_by_tag(self, secrets_client):
        response = _call(get_application_secrets, 'viewer_a')
        assert response['statusCode'] == 200
        assert _body(response) == {'secrets': [{
            'key': 'admin_password',
            'secret_name': f'{APP_PREFIX}admin_password',
            'description': 'd',
            'created_at': '2026-01-02T03:04:05Z',
        }]}
        secrets_client.list_secrets.assert_called_once_with(Filters=[
            {'Key': 'tag-key', 'Values': ['application_id']},
            {'Key': 'tag-value', 'Values': [APP_ID]},
        ])

    def test_empty(self, secrets_client):
        secrets_client.list_secrets.return_value = {'SecretList': []}
        response = _call(get_application_secrets, 'viewer_a')
        assert response['statusCode'] == 200
        assert _body(response) == {'secrets': []}

    def test_list_failure_500(self, secrets_client):
        secrets_client.list_secrets.side_effect = _client_error('InternalServiceError', 'ListSecrets')
        response = _call(get_application_secrets, 'viewer_a')
        assert response['statusCode'] == 500
        assert _body(response)['error'] == 'Failed to list secrets'

    @pytest.mark.parametrize('caller', ['viewer_a', 'executor_a', 'editor_a', 'lead_a', 'admin', 'client_a'])
    def test_allowed(self, caller):
        assert _call(get_application_secrets, caller)['statusCode'] == 200

    @pytest.mark.parametrize('caller', ['viewer_b', 'editor_b', 'client_unbound', 'no_team'])
    def test_other_team_403(self, caller, secrets_client):
        assert _call(get_application_secrets, caller)['statusCode'] == 403
        secrets_client.list_secrets.assert_not_called()

    def test_shared_view_allowed(self):
        assert _call(get_application_secrets, 'viewer_b', shares=share('view'))['statusCode'] == 200

    def test_write_scope_alone_is_not_enough(self, secrets_client):
        assert _call(get_application_secrets, 'editor_a', scopes=WRITE)['statusCode'] == 403
        secrets_client.list_secrets.assert_not_called()

    def test_worker_403(self, secrets_client):
        assert _call(get_application_secrets, 'worker')['statusCode'] == 403
        secrets_client.list_secrets.assert_not_called()

    def test_unknown_application_404(self, secrets_client):
        assert _call(get_application_secrets, 'admin', app_id='app-unknown')['statusCode'] == 404
        secrets_client.list_secrets.assert_not_called()


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------


class TestPutApplicationSecrets:
    BODY = {'secrets': [{'key': 'admin_password', 'value': 'v1'}, {'key': 'api.key-2', 'value': 'v2'}]}

    def test_creates_new_secrets(self, secrets_client):
        response = _call(put_application_secrets, 'editor_a', body=self.BODY)
        assert response['statusCode'] == 201
        assert _body(response) == {'created': ['admin_password', 'api.key-2'], 'updated': []}
        names = [c.kwargs['Name'] for c in secrets_client.create_secret.call_args_list]
        assert names == [f'{APP_PREFIX}admin_password', f'{APP_PREFIX}api.key-2']
        first = secrets_client.create_secret.call_args_list[0].kwargs
        assert first['SecretString'] == 'v1'
        assert first['Description'] == f'Secret for application {APP_ID}'
        assert first['Tags'] == [
            {'Key': 'application_id', 'Value': APP_ID},
            {'Key': 'managed_by', 'Value': PREFIX},
        ]
        secrets_client.update_secret.assert_not_called()

    def test_updates_existing_secret(self, secrets_client):
        secrets_client.create_secret.side_effect = [_client_error('ResourceExistsException'), {}]
        response = _call(put_application_secrets, 'editor_a', body=self.BODY)
        assert response['statusCode'] == 201
        assert _body(response) == {'created': ['api.key-2'], 'updated': ['admin_password']}
        secrets_client.update_secret.assert_called_once_with(
            SecretId=f'{APP_PREFIX}admin_password', SecretString='v1')

    @pytest.mark.parametrize('key', ['../other/key', 'a/b', 'a b', 'k@y', 'x' * 129, '', 'é'])
    def test_invalid_key_400_writes_nothing(self, secrets_client, key):
        body = {'secrets': [{'key': 'ok', 'value': 'v'}, {'key': key, 'value': 'v'}]}
        response = _call(put_application_secrets, 'editor_a', body=body)
        assert response['statusCode'] == 400
        assert 'Invalid secret key' in _body(response)['error']
        secrets_client.create_secret.assert_not_called()

    @pytest.mark.parametrize('value', ['', None, 42])
    def test_empty_value_400_writes_nothing(self, secrets_client, value):
        body = {'secrets': [{'key': 'ok', 'value': 'v'}, {'key': 'other', 'value': value}]}
        response = _call(put_application_secrets, 'editor_a', body=body)
        assert response['statusCode'] == 400
        assert 'value' in _body(response)['error']
        secrets_client.create_secret.assert_not_called()

    def test_missing_key_400(self, secrets_client):
        response = _call(put_application_secrets, 'editor_a', body={'secrets': [{'value': 'v'}]})
        assert response['statusCode'] == 400
        secrets_client.create_secret.assert_not_called()

    @pytest.mark.parametrize('body', [{}, {'secrets': []}, {'secrets': 'nope'}, {'secrets': [1]}])
    def test_malformed_body_400(self, secrets_client, body):
        assert _call(put_application_secrets, 'editor_a', body=body)['statusCode'] == 400
        secrets_client.create_secret.assert_not_called()

    def test_invalid_json_400(self, secrets_client):
        assert _call(put_application_secrets, 'editor_a', body='{not json')['statusCode'] == 400
        secrets_client.create_secret.assert_not_called()

    def test_duplicate_keys_400(self, secrets_client):
        body = {'secrets': [{'key': 'k', 'value': 'a'}, {'key': 'k', 'value': 'b'}]}
        response = _call(put_application_secrets, 'editor_a', body=body)
        assert response['statusCode'] == 400
        assert 'Duplicate' in _body(response)['error']
        secrets_client.create_secret.assert_not_called()

    def test_secrets_manager_failure_500_without_value(self, secrets_client, caplog):
        secrets_client.create_secret.side_effect = _client_error('AccessDeniedException')
        with caplog.at_level(logging.INFO):
            response = _call(put_application_secrets, 'editor_a', body=self.BODY)
        assert response['statusCode'] == 500
        assert _body(response)['error'] == 'Failed to create or update secret admin_password'
        assert all('v1' not in r.getMessage() and 'v2' not in r.getMessage() for r in caplog.records)
        assert any('AccessDeniedException' in r.getMessage() for r in caplog.records)

    def test_values_never_logged(self, secrets_client, caplog):
        with caplog.at_level(logging.DEBUG):
            _call(put_application_secrets, 'editor_a', body={'secrets': [{'key': 'k', 'value': 'sup3r-s3cret'}]})
        assert all('sup3r-s3cret' not in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize('caller', ['editor_a', 'lead_a', 'admin', 'client_a'])
    def test_allowed(self, caller):
        assert _call(put_application_secrets, caller, body=self.BODY)['statusCode'] == 201

    @pytest.mark.parametrize('caller', ['viewer_a', 'executor_a', 'editor_b', 'client_unbound', 'worker', 'no_team'])
    def test_denied_403(self, caller, secrets_client):
        assert _call(put_application_secrets, caller, body=self.BODY)['statusCode'] == 403
        secrets_client.create_secret.assert_not_called()
        secrets_client.update_secret.assert_not_called()

    def test_shared_execute_cannot_write(self, secrets_client):
        assert _call(put_application_secrets, 'editor_b', body=self.BODY, shares=share('execute'))['statusCode'] == 403
        secrets_client.create_secret.assert_not_called()

    def test_shared_full_can_write(self):
        assert _call(put_application_secrets, 'editor_b', body=self.BODY, shares=share('full'))['statusCode'] == 201

    def test_read_scope_alone_is_not_enough(self, secrets_client):
        assert _call(put_application_secrets, 'editor_a', body=self.BODY, scopes=READ)['statusCode'] == 403
        secrets_client.create_secret.assert_not_called()

    def test_unknown_application_404(self, secrets_client):
        assert _call(put_application_secrets, 'admin', body=self.BODY, app_id='app-unknown')['statusCode'] == 404
        secrets_client.create_secret.assert_not_called()


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteApplicationSecrets:
    BODY = {'secret_key': 'admin_password'}

    def test_deletes_without_recovery_and_returns_204(self, secrets_client):
        response = _call(delete_application_secrets, 'editor_a', body=self.BODY)
        assert response['statusCode'] == 204
        assert response['body'] == ''
        secrets_client.delete_secret.assert_called_once_with(
            SecretId=f'{APP_PREFIX}admin_password', ForceDeleteWithoutRecovery=True)

    @pytest.mark.parametrize('key', ['../other/key', 'a/b', 'a b', 'x' * 129, 'é'])
    def test_invalid_key_400(self, secrets_client, key):
        response = _call(delete_application_secrets, 'editor_a', body={'secret_key': key})
        assert response['statusCode'] == 400
        assert 'Invalid secret key' in _body(response)['error']
        secrets_client.delete_secret.assert_not_called()

    @pytest.mark.parametrize('body', [{}, {'secret_key': ''}, {'secret_key': 7}])
    def test_missing_key_400(self, secrets_client, body):
        assert _call(delete_application_secrets, 'editor_a', body=body)['statusCode'] == 400
        secrets_client.delete_secret.assert_not_called()

    def test_invalid_json_400(self, secrets_client):
        assert _call(delete_application_secrets, 'editor_a', body='{not json')['statusCode'] == 400
        secrets_client.delete_secret.assert_not_called()

    def test_unknown_secret_404(self, secrets_client):
        secrets_client.delete_secret.side_effect = _client_error('ResourceNotFoundException', 'DeleteSecret')
        response = _call(delete_application_secrets, 'editor_a', body=self.BODY)
        assert response['statusCode'] == 404
        assert 'not found' in _body(response)['error']

    def test_secrets_manager_failure_500(self, secrets_client):
        secrets_client.delete_secret.side_effect = _client_error('InternalServiceError', 'DeleteSecret')
        response = _call(delete_application_secrets, 'editor_a', body=self.BODY)
        assert response['statusCode'] == 500
        assert _body(response)['error'] == 'Failed to delete secret admin_password'

    @pytest.mark.parametrize('caller', ['editor_a', 'lead_a', 'admin', 'client_a'])
    def test_allowed(self, caller):
        assert _call(delete_application_secrets, caller, body=self.BODY)['statusCode'] == 204

    @pytest.mark.parametrize('caller', ['viewer_a', 'executor_a', 'editor_b', 'client_unbound', 'worker', 'no_team'])
    def test_denied_403(self, caller, secrets_client):
        assert _call(delete_application_secrets, caller, body=self.BODY)['statusCode'] == 403
        secrets_client.delete_secret.assert_not_called()

    def test_shared_execute_cannot_delete(self, secrets_client):
        assert _call(delete_application_secrets, 'editor_b', body=self.BODY, shares=share('execute'))['statusCode'] == 403
        secrets_client.delete_secret.assert_not_called()

    def test_shared_full_can_delete(self):
        assert _call(delete_application_secrets, 'editor_b', body=self.BODY, shares=share('full'))['statusCode'] == 204

    def test_read_scope_alone_is_not_enough(self, secrets_client):
        assert _call(delete_application_secrets, 'editor_a', body=self.BODY, scopes=READ)['statusCode'] == 403
        secrets_client.delete_secret.assert_not_called()

    def test_unknown_application_404(self, secrets_client):
        assert _call(delete_application_secrets, 'admin', body=self.BODY, app_id='app-unknown')['statusCode'] == 404
        secrets_client.delete_secret.assert_not_called()
