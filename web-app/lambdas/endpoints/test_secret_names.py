"""Unit tests for secret_names: Secrets Manager naming, tag listing and upsert."""
import os
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, call

import pytest
from botocore.exceptions import ClientError

import secret_names
from secret_names import (
    SECRET_KEY_PATTERN,
    application_secret_name,
    application_secret_prefix,
    list_secrets_by_tag,
    upsert_secret,
    usecase_secret_name,
    usecase_secret_prefix,
)

ENDPOINTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Every Lambda that builds a Secrets Manager name must go through secret_names.
SECRET_LAMBDAS = [
    'create_usecase_secrets.py',
    'update_usecase_secrets.py',
    'delete_usecase_secrets.py',
    'get_usecase_secrets.py',
    'get_usecase_secret_value.py',
    os.path.join('handlers', 'get_application_secrets.py'),
    os.path.join('handlers', 'put_application_secrets.py'),
    os.path.join('handlers', 'delete_application_secrets.py'),
]


class TestNames:
    def test_usecase_secret_name(self):
        assert usecase_secret_name('qa', 'uc-1', 'password') == 'qa/usecase/uc-1/password'

    def test_application_secret_name(self):
        assert application_secret_name('qa', 'app-1', 'password') == 'qa/application/app-1/password'

    def test_prefixes_end_with_slash_and_match_names(self):
        assert usecase_secret_prefix('qa', 'uc-1') == 'qa/usecase/uc-1/'
        assert application_secret_prefix('qa', 'app-1') == 'qa/application/app-1/'
        assert usecase_secret_name('qa', 'uc-1', 'k').startswith(usecase_secret_prefix('qa', 'uc-1'))
        assert application_secret_name('qa', 'app-1', 'k').startswith(application_secret_prefix('qa', 'app-1'))

    def test_usecase_and_application_namespaces_never_collide(self):
        assert usecase_secret_name('qa', 'x', 'k') != application_secret_name('qa', 'x', 'k')


class TestSecretKeyPattern:
    @pytest.mark.parametrize('key', ['my_password', 'API.KEY-1', 'x' * 128, 'a'])
    def test_valid(self, key):
        assert SECRET_KEY_PATTERN.match(key)

    @pytest.mark.parametrize('key', ['', '../other/key', 'a/b', 'a b', 'k@y', 'x' * 129, 'é'])
    def test_invalid(self, key):
        assert not SECRET_KEY_PATTERN.match(key)


def _secret(name, created=None, description=''):
    item = {'Name': name, 'Description': description}
    if created is not None:
        item['CreatedDate'] = created
    return item


class TestListSecretsByTag:
    def test_filters_by_tag_and_strips_prefix(self):
        client = MagicMock()
        client.list_secrets.return_value = {'SecretList': [
            _secret('qa/usecase/uc-1/user', datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc), 'desc'),
            _secret('qa/usecase/uc-1/password'),
            _secret('qa/usecase/uc-other/user'),  # tag collision on another prefix is skipped
        ]}

        result = list_secrets_by_tag(client, 'usecase_id', 'uc-1', 'qa/usecase/uc-1/')

        assert result == [
            {'key': 'user', 'secret_name': 'qa/usecase/uc-1/user', 'description': 'desc',
             'created_at': '2026-01-02T03:04:05Z'},
            {'key': 'password', 'secret_name': 'qa/usecase/uc-1/password', 'description': '',
             'created_at': ''},
        ]
        client.list_secrets.assert_called_once_with(Filters=[
            {'Key': 'tag-key', 'Values': ['usecase_id']},
            {'Key': 'tag-value', 'Values': ['uc-1']},
        ])

    def test_follows_next_token(self):
        client = MagicMock()
        client.list_secrets.side_effect = [
            {'SecretList': [_secret('qa/application/app-1/a')], 'NextToken': 'page-2'},
            {'SecretList': [_secret('qa/application/app-1/b')]},
        ]

        result = list_secrets_by_tag(client, 'application_id', 'app-1', 'qa/application/app-1/')

        assert [r['key'] for r in result] == ['a', 'b']
        filters = [
            {'Key': 'tag-key', 'Values': ['application_id']},
            {'Key': 'tag-value', 'Values': ['app-1']},
        ]
        assert client.list_secrets.call_args_list == [
            call(Filters=filters),
            call(Filters=filters, NextToken='page-2'),
        ]

    def test_empty(self):
        client = MagicMock()
        client.list_secrets.return_value = {'SecretList': []}
        assert list_secrets_by_tag(client, 'usecase_id', 'uc-1', 'qa/usecase/uc-1/') == []

    def test_non_datetime_created_date_is_blank(self):
        client = MagicMock()
        client.list_secrets.return_value = {'SecretList': [_secret('qa/usecase/uc-1/k', created='not-a-date')]}
        assert list_secrets_by_tag(client, 'usecase_id', 'uc-1', 'qa/usecase/uc-1/')[0]['created_at'] == ''

    def test_bare_magicmock_client_terminates(self):
        # Route-access tests drive handlers with an unconfigured MagicMock client;
        # its `.get('NextToken')` is a truthy mock and must not be treated as a page.
        assert list_secrets_by_tag(MagicMock(), 'usecase_id', 'uc-1', 'qa/usecase/uc-1/') == []


def _client_error(code):
    return ClientError({'Error': {'Code': code, 'Message': code}}, 'CreateSecret')


class TestUpsertSecret:
    TAGS = [{'Key': 'usecase_id', 'Value': 'uc-1'}]

    def test_creates_when_missing(self):
        client = MagicMock()
        assert upsert_secret(client, 'qa/usecase/uc-1/k', 'v', 'desc', self.TAGS) == 'created'
        client.create_secret.assert_called_once_with(
            Name='qa/usecase/uc-1/k', SecretString='v', Description='desc', Tags=self.TAGS)
        client.update_secret.assert_not_called()

    def test_updates_when_exists(self):
        client = MagicMock()
        client.create_secret.side_effect = _client_error('ResourceExistsException')
        assert upsert_secret(client, 'qa/usecase/uc-1/k', 'v', 'desc', self.TAGS) == 'updated'
        client.update_secret.assert_called_once_with(SecretId='qa/usecase/uc-1/k', SecretString='v')

    def test_other_create_error_propagates(self):
        client = MagicMock()
        client.create_secret.side_effect = _client_error('AccessDeniedException')
        with pytest.raises(ClientError):
            upsert_secret(client, 'qa/usecase/uc-1/k', 'v', 'desc', self.TAGS)
        client.update_secret.assert_not_called()

    def test_update_error_propagates(self):
        client = MagicMock()
        client.create_secret.side_effect = _client_error('ResourceExistsException')
        client.update_secret.side_effect = _client_error('InternalServiceError')
        with pytest.raises(ClientError):
            upsert_secret(client, 'qa/usecase/uc-1/k', 'v', 'desc', self.TAGS)


class TestNoInlineSecretNames:
    """Grep guard: secret Lambdas never build `.../usecase/...` or `.../application/...` names inline."""

    INLINE_NAME = re.compile(r'''f["'][^"']*/(usecase|application)/''')

    @pytest.mark.parametrize('filename', SECRET_LAMBDAS)
    def test_no_inline_fstring_secret_name(self, filename):
        with open(os.path.join(ENDPOINTS_DIR, filename), encoding='utf-8') as fh:
            source = fh.read()
        assert not self.INLINE_NAME.search(source), f'{filename} builds a secret name inline'
        assert 'secret_names' in source, f'{filename} does not import secret_names'

    def test_pattern_lives_only_in_secret_names(self):
        for filename in SECRET_LAMBDAS:
            with open(os.path.join(ENDPOINTS_DIR, filename), encoding='utf-8') as fh:
                assert 're.compile(' not in fh.read(), f'{filename} defines its own key pattern'
        assert secret_names.SECRET_KEY_PATTERN.pattern == r'^[A-Za-z0-9_.-]{1,128}$'
