"""
Cross-team access for every /usecase/{id}/... route (H-2, Appendix A).

Each route is driven through its real handler with boto3 mocked. A denied
caller must get 403 (or 404 for an unknown use case) before the handler
touches AWS; an allowed caller must get past authorization.
"""
import importlib
import json
from unittest.mock import MagicMock, patch

import pytest

from authz_test_support import (
    ALL_SCOPES, APP_ID, TEAM_B, UC_ID, make_event, owned_resources, share, worker_header,
)

# (module, action, allow_worker, required scope, extra path params, body)
ROUTES = [
    ('get_usecase', 'view', True, 'api/usecases.read', {}, None),
    ('update_usecase', 'edit', False, 'api/usecases.write', {}, {'name': 'n'}),
    ('delete_usecase', 'delete', False, 'api/usecases.write', {}, None),
    ('create_step', 'edit', False, 'api/usecases.write', {}, {'sort': 1, 'instruction': 'x'}),
    ('list_steps', 'view', True, 'api/usecases.read', {}, None),
    ('update_step', 'edit', False, 'api/usecases.write', {'stepId': 's1'},
     {'instruction': 'x', 'step_type': 'navigation'}),
    ('delete_step', 'edit', False, 'api/usecases.write', {'stepId': 's1'}, None),
    ('reorder_steps', 'edit', False, 'api/usecases.write', {}, {'step_orders': [{'step_id': 'STEP#s1', 'sort': 1}]}),
    ('update_step_from_template', 'edit', False, 'api/usecases.write', {'stepId': 's1'}, {}),
    ('create_trajectory_upload_url', 'execute', True, 'api/executions.write', {'stepId': 's1'}, None),
    ('get_trajectory_download_url', 'view', True, 'api/executions.read', {'stepId': 's1'}, None),
    ('create_usecase_variables', 'edit', False, 'api/usecases.write', {}, {'variables': []}),
    ('get_usecase_variables', 'view', True, 'api/usecases.read', {}, None),
    ('create_schedule', 'edit', False, 'api/usecases.write', {}, {'rate': 1, 'unit': 'hours'}),
    ('get_schedule', 'view', False, 'api/usecases.read', {}, None),
    ('delete_schedule', 'edit', False, 'api/usecases.write', {}, None),
    ('create_usecase_hooks', 'edit', False, 'api/usecases.write', {}, {'before_script': ''}),
    ('get_usecase_hooks', 'view', False, 'api/usecases.read', {}, None),
    ('create_usecase_headers', 'edit', False, 'api/usecases.write', {}, {'headers': {}}),
    ('get_usecase_headers', 'view', False, 'api/usecases.read', {}, None),
    ('export_usecase', 'view', False, 'api/usecases.read', {}, None),
    ('clone_usecase', 'view', False, 'api/usecases.write', {}, {'name': 'copy'}),
    ('get_usecase_subscription', 'view', False, 'api/usecases.read', {}, None),
    ('subscribe_usecase', 'view', False, 'api/usecases.write', {}, None),
    ('unsubscribe_usecase', 'view', False, 'api/usecases.write', {}, None),
    ('import_template', 'edit', False, 'api/usecases.write', {}, {'template_id': 't1'}),
    ('check_template_updates', 'view', False, 'api/templates.read', {}, None),
    ('get_usecase_secrets', 'view', True, 'api/usecases.read', {}, None),
    ('get_usecase_secret_value', 'execute', True, 'api/usecases.execute', {'secret_key': 'k'}, None),
    ('create_usecase_secrets', 'edit', False, 'api/usecases.write', {}, {'secrets': []}),
    ('update_usecase_secrets', 'edit', False, 'api/usecases.write', {}, {'secret_key': 'k', 'value': 'v'}),
    ('delete_usecase_secrets', 'edit', False, 'api/usecases.write', {}, {'secret_key': 'k'}),
]
ROUTE_IDS = [r[0] for r in ROUTES]

# Lowest owner-team caller allowed for an action, and one just below it.
MIN_CALLER = {'view': 'viewer_a', 'execute': 'executor_a', 'edit': 'editor_a', 'delete': 'editor_a'}
BELOW_CALLER = {'view': 'no_team', 'execute': 'viewer_a', 'edit': 'executor_a', 'delete': 'executor_a'}
# Lowest shared-access level that allows an action, and one below it.
MIN_SHARE = {'view': 'view', 'execute': 'execute', 'edit': 'full', 'delete': 'full'}
BELOW_SHARE = {'execute': 'view', 'edit': 'execute', 'delete': 'execute'}


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    """boto3 fully mocked; module-level clients replaced too."""
    for name, value in {'TABLE_NAME': 't', 'SECRET_PREFIX': 'p', 'BUCKET_NAME': 'b', 'S3_BUCKET': 'b',
                        'SCHEDULER_GROUP_NAME': 'g', 'EXECUTE_USECASE_LAMBDA_ARN': 'arn:x',
                        'SCHEDULER_TARGET_ROLE_ARN': 'arn:r', 'SNS_TOPIC_ARN': 'arn:sns'}.items():
        monkeypatch.setenv(name, value)
    resource, client = MagicMock(name='resource'), MagicMock(name='client')
    for module in ('create_trajectory_upload_url', 'get_trajectory_download_url'):
        monkeypatch.setattr(f'{module}._dynamodb', client, raising=False)
        monkeypatch.setattr(f'{module}._s3', client, raising=False)
    with patch('boto3.resource', resource), patch('boto3.client', client):
        yield resource, client


def _call(route, caller, scopes=ALL_SCOPES, usecase_id=UC_ID, header=None, **owned):
    module, _, _, _, extra_path, body = route
    handler = importlib.import_module(module).handler
    event = make_event(caller, path={'id': usecase_id, **extra_path}, body=body, scopes=scopes,
                       worker_header=header)
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
class TestUsecaseRouteAccess:
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

    def test_share_of_another_app_denied(self, route, aws):
        _assert_denied(_call(route, 'editor_b', shares=share('full', app_id='app-other')), aws)

    def test_orphan_usecase_admin_only(self, route, aws):
        _assert_denied(_call(route, 'editor_a', usecase_app=''), aws)

    def test_orphan_usecase_admin_allowed(self, route, aws):
        _assert_allowed(_call(route, 'admin', usecase_app=''), aws)

    def test_unknown_usecase_404(self, route, aws):
        _assert_denied(_call(route, 'admin', usecase_id='uc-unknown'), aws, status=404)

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


class TestUpdateUsecaseTargetApp:
    """N-5: moving a use case needs edit on the target app; only admins clear it."""

    def _update(self, caller, body, target_owner=TEAM_B, **owned):
        def app_ownership(app_id):
            return {APP_ID: {'owner_team_id': 'team-a'}, 'app-b': {'owner_team_id': target_owner}}.get(app_id)
        import update_usecase
        event = make_event(caller, path={'id': UC_ID}, body=body)
        with owned_resources(**owned), \
                patch('resource_auth.get_app_ownership', side_effect=app_ownership), \
                patch('update_usecase.get_usecase_owner', return_value={'application_id': APP_ID}):
            return update_usecase.handler(event, None)

    def _update_call(self, aws):
        table = aws[0].return_value.Table.return_value
        return table.update_item.call_args.kwargs if table.update_item.called else None

    def test_move_to_other_team_app_denied(self, aws):
        response = self._update('editor_a', {'name': 'n', 'application_id': 'app-b'})
        assert response['statusCode'] == 403
        assert self._update_call(aws) is None

    def test_move_to_unknown_app_404(self, aws):
        response = self._update('editor_a', {'name': 'n', 'application_id': 'app-missing'})
        assert response['statusCode'] == 404

    def test_move_with_edit_on_both_restamps_owner(self, aws):
        response = self._update('editor_a', {'name': 'n', 'application_id': 'app-b'}, target_owner='team-a')
        assert response['statusCode'] == 200
        call = self._update_call(aws)
        assert ':owner_team_id' in call['ExpressionAttributeValues']
        assert call['ExpressionAttributeValues'][':owner_team_id'] == 'team-a'
        assert call['ExpressionAttributeValues'][':application_id'] == 'app-b'

    def test_move_with_shared_full_on_target(self, aws):
        # editor_a also needs edit on app-b, owned by team-b and shared at full with team-a
        with patch('resource_auth.list_shared_access',
                   return_value=[{'app_id': 'app-b', 'target_team_id': 'team-a', 'level': 'full'}]):
            import update_usecase
            event = make_event('editor_a', path={'id': UC_ID}, body={'name': 'n', 'application_id': 'app-b'})
            with patch('resource_auth.get_usecase_owner',
                       return_value={'application_id': APP_ID, 'owner_team_id': 'team-a'}), \
                    patch('resource_auth.get_app_ownership', return_value={'owner_team_id': TEAM_B}), \
                    patch('update_usecase.get_usecase_owner', return_value={'application_id': APP_ID}):
                response = update_usecase.handler(event, None)
        assert response['statusCode'] == 200
        assert self._update_call(aws)['ExpressionAttributeValues'][':owner_team_id'] == TEAM_B

    def test_same_app_needs_no_extra_check(self, aws):
        response = self._update('editor_a', {'name': 'n', 'application_id': APP_ID})
        assert response['statusCode'] == 200
        assert ':owner_team_id' not in self._update_call(aws)['ExpressionAttributeValues']

    def test_non_admin_cannot_clear_application(self, aws):
        response = self._update('editor_a', {'name': 'n', 'application_id': ''})
        assert response['statusCode'] == 403
        assert self._update_call(aws) is None

    def test_admin_can_clear_application_and_owner(self, aws):
        response = self._update('admin', {'name': 'n', 'application_id': ''})
        assert response['statusCode'] == 200
        call = self._update_call(aws)
        assert call['ExpressionAttributeValues'][':application_id'] == ''
        assert call['UpdateExpression'].endswith(' REMOVE owner_team_id')


class TestCloneTargetApp:
    """clone = view on the source + edit on the target app (default: the source's app)."""

    def _clone(self, caller, body, aws, shares=None, app_owners=None):
        import clone_usecase
        table = aws[0].return_value.Table.return_value
        table.get_item.return_value = {'Item': {'application_id': APP_ID, 'name': 'src'}}
        table.query.return_value = {'Items': []}
        aws[1].return_value.list_secrets.return_value = {'SecretList': []}
        owners = app_owners or {APP_ID: 'team-a'}
        event = make_event(caller, path={'id': UC_ID}, body=body)
        with owned_resources(shares=shares), \
                patch('resource_auth.get_app_ownership',
                      side_effect=lambda a: {'owner_team_id': owners[a]} if a in owners else None):
            response = clone_usecase.handler(event, None)
        puts = [c.kwargs['Item'] for c in table.put_item.call_args_list]
        return response, next((p for p in puts if p.get('pk') == 'USECASES'), None)

    def test_clone_lands_in_source_app(self, aws):
        response, new_uc = self._clone('editor_a', {'name': 'copy'}, aws)
        assert response['statusCode'] == 200
        assert new_uc['application_id'] == APP_ID
        assert new_uc['owner_team_id'] == 'team-a'

    def test_viewer_cannot_clone_into_source_app(self, aws):
        response, new_uc = self._clone('viewer_a', {'name': 'copy'}, aws)
        assert response['statusCode'] == 403
        assert new_uc is None

    def test_shared_viewer_team_clones_into_own_app(self, aws):
        response, new_uc = self._clone('editor_b', {'name': 'copy', 'application_id': 'app-b'}, aws,
                                       shares=share('view'), app_owners={APP_ID: 'team-a', 'app-b': TEAM_B})
        assert response['statusCode'] == 200
        assert new_uc['application_id'] == 'app-b'
        assert new_uc['owner_team_id'] == TEAM_B

    def test_cannot_clone_into_foreign_app(self, aws):
        response, new_uc = self._clone('editor_a', {'name': 'copy', 'application_id': 'app-b'}, aws,
                                       app_owners={APP_ID: 'team-a', 'app-b': TEAM_B})
        assert response['statusCode'] == 403
        assert new_uc is None


class TestCreateUsecaseTargetApp:
    def _create(self, caller, body, aws):
        import create_usecase
        aws[0].return_value.Table.return_value.get_item.return_value = {'Item': {'owner_team_id': 'team-a'}}
        with owned_resources():
            return create_usecase.handler(make_event(caller, body=body), None)

    def test_editor_creates_in_own_app(self, aws):
        response = self._create('editor_a', {'name': 'n', 'application_id': APP_ID}, aws)
        assert response['statusCode'] == 201
        assert json.loads(response['body'])['application_id'] == APP_ID

    @pytest.mark.parametrize('caller', ['executor_a', 'editor_b', 'client_unbound', 'worker'])
    def test_denied(self, caller, aws):
        response = self._create(caller, {'name': 'n', 'application_id': APP_ID}, aws)
        assert response['statusCode'] == 403
        assert not aws[0].mock_calls

    def test_missing_application_400(self, aws):
        response = self._create('editor_a', {'name': 'n'}, aws)
        assert response['statusCode'] == 400

    def test_unknown_application_404(self, aws):
        response = self._create('editor_a', {'name': 'n', 'application_id': 'app-missing'}, aws)
        assert response['statusCode'] == 404


class TestCreateStepPathBinding:
    def test_body_usecase_mismatch_400(self, aws):
        import create_step
        event = make_event('editor_a', path={'id': UC_ID},
                           body={'usecaseId': 'uc-other', 'sort': 1, 'instruction': 'x'})
        with owned_resources():
            response = create_step.handler(event, None)
        assert response['statusCode'] == 400
        assert not aws[0].return_value.Table.return_value.put_item.called

    def test_step_written_under_path_usecase(self, aws):
        import create_step
        event = make_event('editor_a', path={'id': UC_ID}, body={'sort': 1, 'instruction': 'x'})
        with owned_resources():
            response = create_step.handler(event, None)
        assert response['statusCode'] == 201
        item = aws[0].return_value.Table.return_value.put_item.call_args.kwargs['Item']
        assert item['pk'] == f'USECASE#{UC_ID}'


class TestTeamEditsUsecaseCreatedByTeamLead:
    """
    Edit rights come from the caller's role in the owning team, not from
    being the creator: a use case of Team A's app created by team lead A1
    can be edited by any other team lead or editor of Team A.
    """
    CREATOR_SUB = 'lead-a1-sub'

    def _create_step(self, caller, sub):
        import create_step
        event = make_event(caller, path={'id': UC_ID}, body={'sort': 1, 'instruction': 'x'}, sub=sub)
        with owned_resources(created_by=self.CREATOR_SUB):
            return create_step.handler(event, None)

    @pytest.mark.parametrize('caller,sub', [('lead_a', 'lead-a2-sub'), ('editor_a', 'editor-a-sub')],
                             ids=['other_team_lead', 'editor_not_creator'])
    def test_same_team_allowed(self, caller, sub, aws):
        response = self._create_step(caller, sub)
        assert response['statusCode'] == 201, response
        assert aws[0].return_value.Table.return_value.put_item.called

    @pytest.mark.parametrize('caller,sub', [('executor_a', 'executor-a-sub'), ('lead_b', 'lead-b-sub')],
                             ids=['same_team_executor', 'other_team_lead'])
    def test_denied(self, caller, sub, aws):
        _assert_denied(self._create_step(caller, sub), aws)


class TestDeletesReturn204:
    @pytest.mark.parametrize('module,extra', [('delete_usecase', {}), ('delete_step', {'stepId': 's1'}),
                                              ('delete_schedule', {})])
    def test_204(self, module, extra, aws):
        aws[0].return_value.Table.return_value.query.return_value = {'Items': []}
        handler = importlib.import_module(module).handler
        with owned_resources():
            response = handler(make_event('editor_a', path={'id': UC_ID, **extra}), None)
        assert response['statusCode'] == 204
        assert response['body'] == ''


class TestListModelsScope:
    def test_requires_usecases_read(self, aws):
        import list_models
        response = list_models.handler(make_event('editor_a', scopes='api/templates.read'), None)
        assert response['statusCode'] == 403
        assert not aws[1].mock_calls

    def test_with_scope_lists(self, aws):
        import list_models
        aws[1].return_value.list_models.return_value = {'modelSummaries': []}
        response = list_models.handler(make_event('viewer_a', scopes='api/usecases.read'), None)
        assert response['statusCode'] == 200
