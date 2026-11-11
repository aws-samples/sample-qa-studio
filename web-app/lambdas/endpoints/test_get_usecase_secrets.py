"""
GET /usecase/{id}/secrets merges use-case secrets with the owning application's
secrets: a use-case key shadows the application key, every row carries `source`.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from authz_test_support import APP_ID, UC_ID, make_event, owned_resources
from get_usecase_secrets import handler

PREFIX = 'p'
UC_PREFIX = f'{PREFIX}/usecase/{UC_ID}/'
APP_PREFIX = f'{PREFIX}/application/{APP_ID}/'
CREATED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _secret(name, description=''):
    return {'Name': name, 'Description': description, 'CreatedDate': CREATED}


def _row(prefix, key, source, description=''):
    return {'key': key, 'secret_name': f'{prefix}{key}', 'description': description,
            'created_at': '2026-01-02T03:04:05Z', 'source': source}


@pytest.fixture(autouse=True)
def usecase_owner():
    with patch('get_usecase_secrets.get_usecase_owner',
               return_value={'application_id': APP_ID, 'owner_team_id': 'team-a'}) as owner:
        yield owner


@pytest.fixture
def secrets_client(monkeypatch):
    monkeypatch.setenv('SECRET_PREFIX', PREFIX)
    client = MagicMock()

    def list_secrets(Filters, **_):
        tag = Filters[0]['Values'][0]
        if tag == 'usecase_id':
            return {'SecretList': [_secret(f'{UC_PREFIX}user', 'uc user'), _secret(f'{UC_PREFIX}token')]}
        return {'SecretList': [_secret(f'{APP_PREFIX}user', 'app user'),
                               _secret(f'{APP_PREFIX}admin_password')]}

    client.list_secrets.side_effect = list_secrets
    with patch('get_usecase_secrets.boto3') as mock_boto3:
        mock_boto3.client.return_value = client
        yield client


def _call(caller='viewer_a', **owned):
    with owned_resources(**owned):
        return handler(make_event(caller, path={'id': UC_ID}), None)


def _rows(response):
    assert response['statusCode'] == 200, response
    return json.loads(response['body'])['secrets']


class TestMerge:
    def test_usecase_rows_first_then_unshadowed_application_rows(self, secrets_client):
        assert _rows(_call()) == [
            _row(UC_PREFIX, 'user', 'usecase', 'uc user'),
            _row(UC_PREFIX, 'token', 'usecase'),
            _row(APP_PREFIX, 'admin_password', 'application'),
        ]

    def test_lists_both_tags(self, secrets_client):
        _call()
        assert secrets_client.list_secrets.call_args_list == [
            call(Filters=[{'Key': 'tag-key', 'Values': ['usecase_id']},
                          {'Key': 'tag-value', 'Values': [UC_ID]}]),
            call(Filters=[{'Key': 'tag-key', 'Values': ['application_id']},
                          {'Key': 'tag-value', 'Values': [APP_ID]}]),
        ]

    def test_only_application_secrets(self, secrets_client):
        def list_secrets(Filters, **_):
            if Filters[0]['Values'][0] == 'usecase_id':
                return {'SecretList': []}
            return {'SecretList': [_secret(f'{APP_PREFIX}admin_password')]}
        secrets_client.list_secrets.side_effect = list_secrets
        assert _rows(_call()) == [_row(APP_PREFIX, 'admin_password', 'application')]

    def test_shadowed_application_key_is_hidden_not_duplicated(self, secrets_client):
        keys = [(r['key'], r['source']) for r in _rows(_call())]
        assert keys.count(('user', 'usecase')) == 1
        assert ('user', 'application') not in keys


class TestLegacyUsecase:
    def test_no_application_lists_usecase_only(self, secrets_client, usecase_owner):
        usecase_owner.return_value = {'application_id': None, 'owner_team_id': None}
        rows = _rows(_call('admin', usecase_app=''))
        assert rows == [_row(UC_PREFIX, 'user', 'usecase', 'uc user'), _row(UC_PREFIX, 'token', 'usecase')]
        secrets_client.list_secrets.assert_called_once()

    def test_unknown_owner_record_lists_usecase_only(self, secrets_client, usecase_owner):
        usecase_owner.return_value = None
        rows = _rows(_call())
        assert [r['source'] for r in rows] == ['usecase', 'usecase']
        secrets_client.list_secrets.assert_called_once()

    def test_empty(self, secrets_client, usecase_owner):
        usecase_owner.return_value = None
        secrets_client.list_secrets.side_effect = None
        secrets_client.list_secrets.return_value = {'SecretList': []}
        assert _rows(_call()) == []


class TestErrors:
    def test_list_failure_500(self, secrets_client):
        secrets_client.list_secrets.side_effect = RuntimeError('boom')
        response = _call()
        assert response['statusCode'] == 500
        assert json.loads(response['body'])['error'] == 'Failed to list secrets'

    def test_application_list_failure_500(self, secrets_client):
        def list_secrets(Filters, **_):
            if Filters[0]['Values'][0] == 'usecase_id':
                return {'SecretList': []}
            raise RuntimeError('boom')
        secrets_client.list_secrets.side_effect = list_secrets
        assert _call()['statusCode'] == 500

    def test_denied_caller_never_lists(self, secrets_client):
        assert _call('viewer_b')['statusCode'] == 403
        secrets_client.list_secrets.assert_not_called()
