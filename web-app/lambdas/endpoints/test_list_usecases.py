"""
GET /usecases: team-scoped list plus per-test-case visibility overrides
(BR-3, decision 12), loaded with one BatchGetItem per 100 use cases.
"""
import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from authz_test_support import APP_ID, TEAM_A, TEAM_B, make_event

USECASES = [
    {'id': 'uc-owned', 'application_id': APP_ID, 'owner_team_id': TEAM_A},
    {'id': 'uc-hidden', 'application_id': APP_ID, 'owner_team_id': TEAM_A},
    {'id': 'uc-editors', 'application_id': APP_ID, 'owner_team_id': TEAM_A},
    {'id': 'uc-shared', 'application_id': 'app-b', 'owner_team_id': TEAM_B},
    {'id': 'uc-foreign', 'application_id': 'app-c', 'owner_team_id': 'team-c'},
    {'id': 'uc-orphan', 'owner_team_id': TEAM_A},
]
OVERRIDES = {
    'uc-hidden': {'allowed_subs': ['someone-else']},
    'uc-editors': {'allowed_roles': ['editor']},
}


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 't')
    resource = MagicMock(name='resource')
    resource.return_value.Table.return_value.query.return_value = {'Items': [dict(u) for u in USECASES]}
    with patch('boto3.resource', resource):
        yield resource


def _list(caller, overrides=OVERRIDES, shared=(), batch_error=None, scopes='api/usecases.read'):
    import list_usecases
    grants = [{'app_id': a} for a in shared]
    batch = patch('resource_auth.batch_get_testcase_overrides',
                  side_effect=batch_error or (lambda ids: {i: overrides[i] for i in ids if i in overrides}))
    with batch as batch_mock, \
            patch('permissions_repo.list_apps_shared_with_team', return_value=grants):
        response = list_usecases.handler(make_event(caller, scopes=scopes), None)
    body = json.loads(response['body'])
    return response['statusCode'], [u['id'] for u in body.get('usecases', [])], batch_mock


def test_viewer_sees_owned_minus_overridden(aws):
    status, ids, _ = _list('viewer_a')
    assert status == 200
    assert ids == ['uc-owned']


def test_editor_sees_role_restricted_use_case(aws):
    _, ids, _ = _list('editor_a')
    assert ids == ['uc-owned', 'uc-editors']


def test_shared_use_cases_listed(aws):
    _, ids, _ = _list('viewer_a', shared=['app-b'])
    assert ids == ['uc-owned', 'uc-shared']


def test_orphan_hidden_for_non_admin(aws):
    _, ids, _ = _list('editor_a', overrides={})
    assert 'uc-orphan' not in ids


def test_admin_sees_everything_without_override_lookup(aws):
    status, ids, batch = _list('admin', scopes='api/admin')
    assert status == 200
    assert ids == [u['id'] for u in USECASES]
    batch.assert_not_called()


def test_one_batch_lookup_for_the_visible_set(aws):
    _, _, batch = _list('editor_a', shared=['app-b'])
    batch.assert_called_once()
    assert sorted(batch.call_args.args[0]) == ['uc-editors', 'uc-hidden', 'uc-owned', 'uc-shared']


def test_override_lookup_error_fails_closed(aws):
    status, ids, _ = _list('editor_a', batch_error=RuntimeError('ddb'))
    assert status == 200
    assert ids == []


def test_no_team_sees_nothing(aws):
    _, ids, batch = _list('no_team')
    assert ids == []
    batch.assert_not_called()


def test_missing_read_scope_403(aws):
    status, _, _ = _list('editor_a', scopes='api/usecases.write')
    assert status == 403


def test_request_headers_not_logged(aws, caplog):
    import list_usecases
    event = make_event('editor_a', headers={'Authorization': 'Bearer secret-token'})
    with caplog.at_level(logging.DEBUG), \
            patch('resource_auth.batch_get_testcase_overrides', return_value={}), \
            patch('permissions_repo.list_apps_shared_with_team', return_value=[]):
        list_usecases.handler(event, None)
    assert 'secret-token' not in caplog.text
