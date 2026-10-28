"""
Cross-team access for every test suite / suite execution route (H-2, Appendix A).

Suites inherit access from their application (orphans are admin-only); a
suite execution must exist under the suite in the path; the worker reaches
suite routes only on runner routes (W) with a capability for a use case
execution of that same suite execution. Denials happen before AWS is touched.
"""
import importlib
import json
from unittest.mock import MagicMock, patch

import pytest

from authz_test_support import (
    ALL_SCOPES, APP_ID, EXEC_ID, SUITE_EXEC_ID, SUITE_ID, TEAM_B, UC_ID,
    execution_record, make_event, owned_resources, share, worker_header,
)

# (module, action, allow_worker, required scope, path kind, extra path params, body)
ROUTES = [
    ('get_test_suite', 'view', False, 'api/suite.read', 'suite', {}, None),
    ('update_test_suite', 'edit', False, 'api/suite.write', 'suite', {}, {'name': 'Suite name'}),
    ('delete_test_suite', 'delete', False, 'api/suite.write', 'suite', {}, None),
    ('list_suite_usecases', 'view', False, 'api/suite.read', 'suite', {}, None),
    ('add_usecases_to_suite', 'edit', False, 'api/suite.write', 'suite', {}, {'usecase_ids': [UC_ID]}),
    ('remove_usecase_from_suite', 'edit', False, 'api/suite.write', 'suite', {'usecase_id': UC_ID}, None),
    ('execute_test_suite', 'execute', False, 'api/executions.write', 'suite', {}, {'trigger_type': 'ci_runner'}),
    ('list_suite_executions', 'view', False, 'api/suite.read', 'suite', {}, None),
    ('update_suite_schedule', 'edit', False, 'api/suite.write', 'suite', {}, {'schedule_enabled': False}),
    ('get_suite_execution', 'view', False, 'api/suite.read', 'sx', {}, None),
    ('update_suite_execution_status', 'execute', True, 'api/executions.write', 'sx', {}, {'status': 'running'}),
    ('generate_suite_artifact_url', 'execute', True, 'api/suite.write', 'sx', {},
     {'type': 'logs', 'filename': 'suite.log', 'content_type': 'text/plain'}),
    ('list_suite_artifacts', 'view', False, 'api/suite.read', 'sx', {}, None),
]
ROUTE_IDS = [r[0] for r in ROUTES]
SX_ROUTES = [r for r in ROUTES if r[4] == 'sx']

MIN_CALLER = {'view': 'viewer_a', 'execute': 'executor_a', 'edit': 'editor_a', 'delete': 'editor_a'}
BELOW_CALLER = {'view': 'no_team', 'execute': 'viewer_a', 'edit': 'executor_a', 'delete': 'executor_a'}
MIN_SHARE = {'view': 'view', 'execute': 'execute', 'edit': 'full', 'delete': 'full'}
BELOW_SHARE = {'execute': 'view', 'edit': 'execute', 'delete': 'execute'}

# The worker's execution belongs to the suite execution in the path.
SUITE_WORKER_EXECUTIONS = {(UC_ID, EXEC_ID): execution_record(suite_id=SUITE_ID, suite_execution_id=SUITE_EXEC_ID)}

_MODULE_CLIENTS = {
    'execute_test_suite': ('dynamodb', 'eventbridge', 'cloudwatch', 'lambda_client'),
    'update_suite_execution_status': ('dynamodb',),
}


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    for name, value in {'TABLE_NAME': 't', 'BUCKET_NAME': 'b', 'S3_BUCKET': 'b',
                        'SCHEDULER_GROUP_NAME': 'g', 'EXECUTE_SUITE_LAMBDA_ARN': 'arn:x'}.items():
        monkeypatch.setenv(name, value)
    resource, client = MagicMock(name='resource'), MagicMock(name='client')
    # Records read by the handlers (suite, use cases) belong to team-a's app.
    resource.return_value.Table.return_value.get_item.return_value = {
        'Item': {'id': UC_ID, 'name': 'n', 'application_id': APP_ID, 'owner_team_id': 'team-a'}}
    for module, attrs in _MODULE_CLIENTS.items():
        for attr in attrs:
            monkeypatch.setattr(f'{module}.{attr}', client)
    with patch('boto3.resource', resource), patch('boto3.client', client):
        yield resource, client


def _call(route, caller, scopes=ALL_SCOPES, suite_id=SUITE_ID, suite_execution_id=SUITE_EXEC_ID,
          header=None, **owned):
    module, _, _, _, kind, extra_path, body = route
    handler = importlib.import_module(module).handler
    path = {'suite_id': suite_id, **extra_path}
    if kind == 'sx':
        path['execution_id'] = suite_execution_id
    event = make_event(caller, path=path, body=body, scopes=scopes, worker_header=header)
    owned.setdefault('executions', SUITE_WORKER_EXECUTIONS)
    with owned_resources(**owned):
        try:
            return handler(event, None)
        except Exception as exc:  # noqa: BLE001 — a crash on mocked AWS data is past authorization
            return {'statusCode': None, 'raised': repr(exc)}


def _assert_denied(response, aws, status=403):
    assert response['statusCode'] == status, response
    resource, client = aws
    assert not resource.mock_calls and not client.mock_calls, 'handler touched AWS before authorization'


def _assert_allowed(response, aws):
    """Past authorization: no 401/403, and any 404 comes from the handler (AWS was read)."""
    assert response['statusCode'] not in (401, 403), response
    if response['statusCode'] == 404:
        resource, client = aws
        assert resource.mock_calls or client.mock_calls, response


@pytest.mark.parametrize('route', ROUTES, ids=ROUTE_IDS)
class TestSuiteRouteAccess:
    def test_min_owner_role_allowed(self, route, aws):
        _assert_allowed(_call(route, MIN_CALLER[route[1]]), aws)

    def test_role_below_required_denied(self, route, aws):
        _assert_denied(_call(route, BELOW_CALLER[route[1]]), aws)

    def test_other_team_editor_denied(self, route, aws):
        _assert_denied(_call(route, 'editor_b'), aws)

    def test_shared_at_required_level_allowed(self, route, aws):
        _assert_allowed(_call(route, 'editor_b', shares=share(MIN_SHARE[route[1]])), aws)

    def test_shared_below_required_level_denied(self, route, aws):
        below = BELOW_SHARE.get(route[1])
        if below is None:
            pytest.skip('view is the lowest share level')
        _assert_denied(_call(route, 'editor_b', shares=share(below)), aws)

    def test_orphan_suite_admin_only(self, route, aws):
        _assert_denied(_call(route, 'editor_a', suite_app=''), aws)

    def test_orphan_suite_admin_allowed(self, route, aws):
        _assert_allowed(_call(route, 'admin', suite_app=''), aws)

    def test_unknown_suite_404(self, route, aws):
        _assert_denied(_call(route, 'admin', suite_id='suite-unknown'), aws, status=404)

    def test_bound_client_allowed(self, route, aws):
        _assert_allowed(_call(route, 'client_a'), aws)

    @pytest.mark.parametrize('caller', ['client_unbound', 'client_b'])
    def test_unbound_or_foreign_client_denied(self, route, aws, caller):
        _assert_denied(_call(route, caller), aws)

    def test_worker_without_capability_denied(self, route, aws):
        _assert_denied(_call(route, 'worker'), aws)

    def test_worker_with_capability(self, route, aws):
        response = _call(route, 'worker', header=worker_header())
        if route[2]:
            _assert_allowed(response, aws)
        else:
            _assert_denied(response, aws)

    def test_missing_route_scope_denied(self, route, aws):
        scopes = ' '.join(s for s in ALL_SCOPES.split() if s != route[3])
        _assert_denied(_call(route, 'editor_a', scopes=scopes), aws)


@pytest.mark.parametrize('route', SX_ROUTES, ids=[r[0] for r in SX_ROUTES])
class TestSuiteExecutionBinding:
    def test_suite_execution_not_under_suite_404(self, route, aws):
        suite_executions = {('suite-other', SUITE_EXEC_ID): {'status': 'running'}}
        _assert_denied(_call(route, 'admin', suite_executions=suite_executions), aws, status=404)

    def test_worker_of_another_suite_execution_denied(self, route, aws):
        executions = {(UC_ID, EXEC_ID): execution_record(suite_id=SUITE_ID, suite_execution_id='sx-other')}
        _assert_denied(_call(route, 'worker', header=worker_header(), executions=executions), aws)

    def test_worker_of_non_suite_execution_denied(self, route, aws):
        executions = {(UC_ID, EXEC_ID): execution_record()}
        _assert_denied(_call(route, 'worker', header=worker_header(), executions=executions), aws)

    def test_worker_finished_execution_denied(self, route, aws):
        executions = {(UC_ID, EXEC_ID): execution_record(status='success', suite_id=SUITE_ID,
                                                         suite_execution_id=SUITE_EXEC_ID)}
        _assert_denied(_call(route, 'worker', header=worker_header(), executions=executions), aws)


def _table(aws):
    return aws[0].return_value.Table.return_value


class TestCreateTestSuite:
    def _create(self, caller, body):
        import create_test_suite
        with owned_resources():
            return create_test_suite.handler(make_event(caller, body=body), None)

    def _body(self, **extra):
        return {'name': 'Smoke suite', 'description': 'd', **extra}

    def test_editor_creates_in_own_app(self, aws):
        _table(aws).get_item.return_value = {'Item': {'owner_team_id': 'team-a'}}
        response = self._create('editor_a', self._body(application_id=APP_ID))
        assert response['statusCode'] == 201
        assert json.loads(response['body'])['owner_team_id'] == 'team-a'

    @pytest.mark.parametrize('caller', ['executor_a', 'editor_b', 'client_unbound', 'worker'])
    def test_denied(self, caller, aws):
        assert self._create(caller, self._body(application_id=APP_ID))['statusCode'] == 403
        assert not aws[0].mock_calls

    def test_missing_application_400(self, aws):
        assert self._create('editor_a', self._body())['statusCode'] == 400

    def test_unknown_application_404(self, aws):
        assert self._create('editor_a', self._body(application_id='app-missing'))['statusCode'] == 404


class TestUpdateTestSuiteTargetApp:
    def _update(self, caller, body, aws, suite_app=APP_ID, app_owners=None):
        import update_test_suite
        _table(aws).get_item.return_value = {'Item': {'application_id': suite_app}}
        _table(aws).update_item.return_value = {'Attributes': {'pk': 'x', 'sk': 'y'}}
        owners = app_owners or {APP_ID: 'team-a', 'app-b': TEAM_B}
        event = make_event(caller, path={'suite_id': SUITE_ID}, body=body)
        with owned_resources(suite_app=suite_app), \
                patch('resource_auth.get_app_ownership',
                      side_effect=lambda a: {'owner_team_id': owners[a]} if a in owners else None):
            return update_test_suite.handler(event, None)

    def _update_call(self, aws):
        return _table(aws).update_item.call_args.kwargs if _table(aws).update_item.called else None

    def test_orphan_suite_no_longer_editable_by_anyone(self, aws):
        # Fail-open removed: a suite without application_id is admin-only.
        response = self._update('editor_a', {'name': 'New name'}, aws, suite_app='')
        assert response['statusCode'] == 403
        assert self._update_call(aws) is None

    def test_move_to_other_team_app_denied(self, aws):
        response = self._update('editor_a', {'application_id': 'app-b'}, aws)
        assert response['statusCode'] == 403
        assert self._update_call(aws) is None

    def test_move_within_own_team_restamps_owner(self, aws):
        response = self._update('editor_a', {'application_id': 'app-a2'}, aws,
                                app_owners={APP_ID: 'team-a', 'app-a2': 'team-a'})
        assert response['statusCode'] == 200
        values = self._update_call(aws)['ExpressionAttributeValues']
        assert values[':application_id'] == 'app-a2'
        assert values[':owner_team_id'] == 'team-a'

    def test_non_admin_cannot_clear_application(self, aws):
        response = self._update('editor_a', {'application_id': ''}, aws)
        assert response['statusCode'] == 403

    def test_admin_clears_application_and_owner(self, aws):
        response = self._update('admin', {'application_id': ''}, aws)
        assert response['statusCode'] == 200
        call = self._update_call(aws)
        assert call['ExpressionAttributeValues'][':application_id'] == ''
        assert call['UpdateExpression'].endswith(' REMOVE owner_team_id')

    def test_admin_adopts_orphan_suite_into_app(self, aws):
        response = self._update('admin', {'application_id': APP_ID}, aws, suite_app='')
        assert response['statusCode'] == 200
        assert self._update_call(aws)['ExpressionAttributeValues'][':owner_team_id'] == 'team-a'


class TestListSuiteUsecasesOverride:
    """Per-test-case overrides narrow the suite's use case list (BR-3)."""

    def _list(self, caller, aws, overrides=None):
        import list_suite_usecases
        table = _table(aws)
        table.get_item.return_value = {'Item': {'application_id': APP_ID, 'owner_team_id': 'team-a'}}
        table.query.return_value = {'Items': [{'usecase_id': UC_ID}, {'usecase_id': 'uc-hidden'}]}
        aws[0].return_value.batch_get_item.return_value = {'Responses': {'t': []}}
        with owned_resources(overrides=overrides):
            response = list_suite_usecases.handler(make_event(caller, path={'suite_id': SUITE_ID}), None)
        return response, [u['usecase_id'] for u in json.loads(response['body'])['usecases']]

    def test_no_override_lists_all(self, aws):
        response, ids = self._list('viewer_a', aws)
        assert response['statusCode'] == 200
        assert ids == [UC_ID, 'uc-hidden']

    def test_override_by_sub_hides_testcase(self, aws):
        _, ids = self._list('viewer_a', aws, overrides={'uc-hidden': {'allowed_subs': ['someone-else']}})
        assert ids == [UC_ID]

    def test_override_by_role_hides_from_other_roles(self, aws):
        overrides = {'uc-hidden': {'allowed_roles': ['editor']}}
        assert self._list('viewer_a', aws, overrides=overrides)[1] == [UC_ID]
        assert self._list('editor_a', aws, overrides=overrides)[1] == [UC_ID, 'uc-hidden']

    def test_admin_bypasses_override(self, aws):
        _, ids = self._list('admin', aws, overrides={'uc-hidden': {'allowed_subs': ['someone-else']}})
        assert ids == [UC_ID, 'uc-hidden']

    def test_overrides_loaded_with_one_batch_call(self, aws):
        import list_suite_usecases
        table = _table(aws)
        table.get_item.return_value = {'Item': {'application_id': APP_ID, 'owner_team_id': 'team-a'}}
        table.query.return_value = {'Items': [{'usecase_id': UC_ID}, {'usecase_id': 'uc-hidden'}]}
        aws[0].return_value.batch_get_item.return_value = {'Responses': {'t': []}}
        with owned_resources(), \
                patch('resource_auth.batch_get_testcase_overrides', return_value={}) as batch, \
                patch('resource_auth.get_testcase_override') as single:
            list_suite_usecases.handler(make_event('viewer_a', path={'suite_id': SUITE_ID}), None)
        batch.assert_called_once()
        assert sorted(batch.call_args.args[0]) == sorted([UC_ID, 'uc-hidden'])
        single.assert_not_called()

    def test_override_lookup_error_hides_all(self, aws):
        import list_suite_usecases
        table = _table(aws)
        table.get_item.return_value = {'Item': {'application_id': APP_ID, 'owner_team_id': 'team-a'}}
        table.query.return_value = {'Items': [{'usecase_id': UC_ID}]}
        with owned_resources(), \
                patch('resource_auth.batch_get_testcase_overrides', side_effect=RuntimeError('ddb')):
            response = list_suite_usecases.handler(make_event('viewer_a', path={'suite_id': SUITE_ID}), None)
        assert json.loads(response['body'])['usecases'] == []


class TestAddUsecasesToSuite:
    """edit on the suite + view on each use case, and the use case must belong to the suite's team."""

    def _add(self, caller, usecase_item, aws, shares=None):
        import add_usecases_to_suite
        table = _table(aws)
        table.get_item.side_effect = [
            {'Item': {'application_id': APP_ID, 'owner_team_id': 'team-a', 'total_usecases': 0}},
            {'Item': usecase_item},
        ]
        table.query.return_value = {'Items': []}
        event = make_event(caller, path={'suite_id': SUITE_ID}, body={'usecase_ids': ['uc-x']})
        with owned_resources(shares=shares), \
                patch('resource_auth.get_app_owner', side_effect=lambda a: {APP_ID: 'team-a', 'app-b': TEAM_B}.get(a)):
            response = add_usecases_to_suite.handler(event, None)
        return response, table.batch_writer.called

    def test_same_team_usecase_added(self, aws):
        response, wrote = self._add('editor_a', {'id': 'uc-x', 'name': 'n', 'application_id': APP_ID}, aws)
        assert response['statusCode'] == 200
        assert wrote

    def test_foreign_usecase_denied(self, aws):
        response, wrote = self._add('editor_a', {'id': 'uc-x', 'application_id': 'app-b'}, aws)
        assert response['statusCode'] == 403
        assert not wrote

    def test_visible_but_other_team_usecase_denied(self, aws):
        # team-a sees app-b through a share, but a team-a suite can't run team-b's use case
        shared = [{'app_id': 'app-b', 'target_team_id': 'team-a', 'level': 'full'}]
        response, wrote = self._add('editor_a', {'id': 'uc-x', 'application_id': 'app-b'}, aws, shares=shared)
        assert response['statusCode'] == 403
        assert 'another team' in json.loads(response['body'])['message']
        assert not wrote

    def test_orphan_usecase_denied(self, aws):
        response, wrote = self._add('editor_a', {'id': 'uc-x'}, aws)
        assert response['statusCode'] == 403
        assert not wrote


class TestExecuteTestSuiteScheduler:
    def test_scheduler_invocation_skips_api_auth(self, aws):
        import execute_test_suite
        aws[1].get_item.return_value = {}
        response = execute_test_suite.handler(
            {'pathParameters': {'suite_id': SUITE_ID}, 'body': json.dumps({'trigger_type': 'scheduled'})}, None)
        assert response['statusCode'] == 404  # reached the suite lookup without an authorizer context


class TestRemoveUsecaseAssociation:
    def _remove(self, caller, aws):
        from handlers import remove_usecase_association
        event = make_event(caller, path={'id': APP_ID, 'usecaseId': UC_ID})
        with owned_resources():
            return remove_usecase_association.handle(event)

    def test_editor_removes_own_app_usecase_204(self, aws):
        _table(aws).update_item.return_value = {'Attributes': {'application_id': APP_ID}}
        response = self._remove('editor_a', aws)
        assert response['statusCode'] == 204
        uc_update = _table(aws).update_item.call_args_list[0].kwargs
        assert uc_update['ConditionExpression'] == 'attribute_exists(pk) AND application_id = :app_id'
        assert uc_update['ExpressionAttributeValues'] == {':app_id': APP_ID}

    @pytest.mark.parametrize('caller', ['executor_a', 'editor_b', 'client_unbound'])
    def test_denied(self, caller, aws):
        assert self._remove(caller, aws)['statusCode'] == 403
        assert not aws[0].mock_calls
