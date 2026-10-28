"""Resource access for the use case secret inventory routes (H-1 / H-2)."""
import json
from unittest.mock import patch, MagicMock

import pytest

import create_usecase_secrets
import delete_usecase_secrets
import get_usecase_secrets
import update_usecase_secrets
from authz_test_support import UC_ID, make_event, owned_resources, share, worker_header


@pytest.fixture(autouse=True)
def secrets_client(monkeypatch):
    monkeypatch.setenv('SECRET_PREFIX', 'p')
    client = MagicMock()
    client.list_secrets.return_value = {'SecretList': [{'Name': f'p/usecase/{UC_ID}/user'}]}
    with patch('boto3.client', return_value=client):
        yield client


def _call(module, caller, body=None, **owned):
    event = make_event(caller, path={'id': UC_ID}, body=body, **({'worker_header': worker_header()}
                                                               if caller == 'worker' else {}))
    with owned_resources(**owned):
        return module.handler(event, None)


_WRITE_BODIES = {
    create_usecase_secrets: {'secrets': [{'key': 'user', 'value': 'v'}]},
    update_usecase_secrets: {'secret_key': 'user', 'value': 'v'},
    delete_usecase_secrets: {'secret_key': 'user'},
}


class TestListSecretKeys:
    @pytest.mark.parametrize('caller', ['viewer_a', 'executor_a', 'editor_a', 'admin', 'client_a', 'worker'])
    def test_allowed(self, caller):
        response = _call(get_usecase_secrets, caller)
        assert response['statusCode'] == 200
        assert json.loads(response['body'])['secrets'][0]['key'] == 'user'

    @pytest.mark.parametrize('caller', ['viewer_b', 'editor_b', 'client_unbound', 'no_team'])
    def test_other_team_403(self, caller, secrets_client):
        assert _call(get_usecase_secrets, caller)['statusCode'] == 403
        secrets_client.list_secrets.assert_not_called()

    def test_shared_view_allowed(self):
        assert _call(get_usecase_secrets, 'viewer_b', shares=share('view'))['statusCode'] == 200

    def test_orphan_admin_only(self):
        assert _call(get_usecase_secrets, 'editor_a', usecase_app='')['statusCode'] == 403


class TestWriteSecrets:
    @pytest.mark.parametrize('module', list(_WRITE_BODIES))
    def test_owner_editor_allowed(self, module):
        expected = 204 if module is delete_usecase_secrets else 200
        assert _call(module, 'editor_a', body=_WRITE_BODIES[module])['statusCode'] == expected

    @pytest.mark.parametrize('module', list(_WRITE_BODIES))
    @pytest.mark.parametrize('caller', ['executor_a', 'viewer_a', 'editor_b', 'client_unbound', 'worker'])
    def test_denied(self, module, caller, secrets_client):
        assert _call(module, caller, body=_WRITE_BODIES[module])['statusCode'] == 403
        secrets_client.create_secret.assert_not_called()
        secrets_client.update_secret.assert_not_called()
        secrets_client.delete_secret.assert_not_called()

    @pytest.mark.parametrize('module', list(_WRITE_BODIES))
    def test_shared_execute_cannot_write(self, module):
        assert _call(module, 'editor_b', body=_WRITE_BODIES[module], shares=share('execute'))['statusCode'] == 403

    @pytest.mark.parametrize('module', list(_WRITE_BODIES))
    def test_shared_full_can_write(self, module):
        expected = 204 if module is delete_usecase_secrets else 200
        assert _call(module, 'editor_b', body=_WRITE_BODIES[module], shares=share('full'))['statusCode'] == expected

    def test_delete_returns_empty_204(self):
        response = _call(delete_usecase_secrets, 'editor_a', body=_WRITE_BODIES[delete_usecase_secrets])
        assert response['statusCode'] == 204
        assert response['body'] == ''
