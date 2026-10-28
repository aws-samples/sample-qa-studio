"""
Cross-team access for every /usecase/{id}/executions/... route (H-2, Appendix A).

The execution must exist under the use case in the path (404 otherwise), the
caller needs the route's action on the owning app, and the worker is only let
through on runner routes (W) with a capability for that same, still active
execution. Denials must happen before the handler touches AWS.
"""
import importlib
from unittest.mock import MagicMock, patch

import pytest

from authz_test_support import (
    ALL_SCOPES, EXEC_ID, UC_ID, execution_record, make_event, owned_resources, share, worker_header,
)

# (module, action, allow_worker, required scope, extra path params, body)
ROUTES = [
    ('list_executions', 'view', False, 'api/executions.read', None, None),
    ('get_execution', 'view', True, 'api/executions.read', {}, None),
    ('delete_execution', 'edit', False, 'api/executions.write', {}, None),
    ('update_execution_status', 'execute', True, 'api/executions.write', {}, {'status': 'running'}),
    ('stop_execution', 'execute', False, 'api/executions.write', {}, None),
    ('request_recording_download', 'view', True, 'api/executions.write', {}, None),
    ('list_execution_steps', 'view', True, 'api/executions.read', {}, None),
    ('get_execution_step', 'view', False, 'api/executions.read', {'stepId': 's1'}, None),
    ('update_execution_step_status', 'execute', True, 'api/executions.write', {'stepId': 's1'},
     {'status': 'running'}),
    ('get_execution_variables', 'view', True, 'api/executions.read', {}, None),
    ('get_live_view', 'view', True, 'api/executions.read', {}, None),
    ('create_live_view', 'execute', True, 'api/executions.write', {}, {'live_view_url': 'https://x'}),
    ('delete_live_view', 'execute', True, 'api/executions.write', {}, None),
    ('create_runtime_variable', 'execute', True, 'api/executions.write', {}, {'key': 'k', 'value': 'v'}),
    ('update_mobile_metadata', 'execute', True, 'api/executions.write', {}, {'device_name': 'd'}),
    ('get_execution_headers', 'view', True, 'api/executions.read', {}, None),
    ('list_downloads', 'view', False, 'api/executions.read', {}, None),
    ('download_file', 'view', False, 'api/executions.read', {'fileName': 'f.txt'}, None),
    ('list_recording_batches', 'view', False, 'api/executions.read', {}, None),
    ('get_recording_batch', 'view', False, 'api/executions.read', {'batchId': 'batch_1'}, None),
    ('get_video_playback', 'view', False, 'api/executions.read', {}, None),
    ('generate_execution_artifact_url', 'execute', True, 'api/executions.write', {},
     {'type': 'logs', 'filename': 'run.log', 'content_type': 'text/plain'}),
    ('list_execution_artifacts', 'view', False, 'api/executions.read', {}, None),
    ('confirm_artifact_upload', 'execute', True, 'api/executions.write', {'artifactId': 'a1'}, {}),
    ('generate_step_artifact_url', 'execute', True, 'api/executions.write', {'stepId': 's1'},
     {'filename': 'shot.png', 'content_type': 'image/png'}),
    ('get_step_trace', 'view', False, 'api/executions.read', {'stepId': '1'}, None),
]
ROUTE_IDS = [r[0] for r in ROUTES]
EXECUTION_ROUTES = [r for r in ROUTES if r[4] is not None]

MIN_CALLER = {'view': 'viewer_a', 'execute': 'executor_a', 'edit': 'editor_a'}
BELOW_CALLER = {'view': 'no_team', 'execute': 'viewer_a', 'edit': 'executor_a'}
MIN_SHARE = {'view': 'view', 'execute': 'execute', 'edit': 'full'}
BELOW_SHARE = {'execute': 'view', 'edit': 'execute'}

_MODULE_CLIENTS = {
    'update_execution_status': ('dynamodb', 'eventbridge'),
    'update_execution_step_status': ('dynamodb',),
    'create_live_view': ('_dynamodb',),
    'delete_live_view': ('_dynamodb',),
    'create_runtime_variable': ('_dynamodb',),
    'update_mobile_metadata': ('_dynamodb',),
    'get_execution_headers': ('_dynamodb',),
    'confirm_artifact_upload': ('dynamodb',),
}


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    """boto3 fully mocked; module-level clients replaced too."""
    for name, value in {'TABLE_NAME': 't', 'BUCKET_NAME': 'b', 'S3_BUCKET': 'b',
                        'DYNAMODB_TABLE_NAME': 't', 'EVENT_BUS_NAME': 'bus'}.items():
        monkeypatch.setenv(name, value)
    resource, client = MagicMock(name='resource'), MagicMock(name='client')
    for module, attrs in _MODULE_CLIENTS.items():
        for attr in attrs:
            monkeypatch.setattr(f'{module}.{attr}', client)
    with patch('boto3.resource', resource), patch('boto3.client', client):
        yield resource, client


def _call(route, caller, scopes=ALL_SCOPES, usecase_id=UC_ID, execution_id=EXEC_ID, header=None, **owned):
    module, _, _, _, extra_path, body = route
    handler = importlib.import_module(module).handler
    path = {'id': usecase_id}
    if extra_path is not None:
        path.update({'executionId': execution_id, **extra_path})
    event = make_event(caller, path=path, body=body, scopes=scopes, worker_header=header)
    event['httpMethod'] = 'GET'  # get_live_view's method guard
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
class TestExecutionRouteAccess:
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

    def test_orphan_usecase_admin_only(self, route, aws):
        _assert_denied(_call(route, 'editor_a', usecase_app=''), aws)
        _assert_allowed(_call(route, 'admin', usecase_app=''), aws)

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


@pytest.mark.parametrize('route', EXECUTION_ROUTES, ids=[r[0] for r in EXECUTION_ROUTES])
class TestExecutionBinding:
    def test_execution_not_under_usecase_404(self, route, aws):
        # EXEC_ID exists, but under another use case: unreachable through UC_ID.
        executions = {('uc-other', EXEC_ID): execution_record()}
        _assert_denied(_call(route, 'admin', executions=executions), aws, status=404)

    def test_unknown_execution_404(self, route, aws):
        _assert_denied(_call(route, 'editor_a', execution_id='ex-unknown'), aws, status=404)

    def test_worker_token_for_other_execution_denied(self, route, aws):
        executions = {(UC_ID, EXEC_ID): execution_record(), (UC_ID, 'ex-other'): execution_record()}
        response = _call(route, 'worker', header=worker_header(execution_id='ex-other'), executions=executions)
        _assert_denied(response, aws)

    def test_worker_token_mismatch_denied(self, route, aws):
        _assert_denied(_call(route, 'worker', header=worker_header(token='forged')), aws)

    @pytest.mark.parametrize('status', ['success', 'failed', 'stopped'])
    def test_worker_finished_execution_denied(self, route, aws, status):
        executions = {(UC_ID, EXEC_ID): execution_record(status=status)}
        _assert_denied(_call(route, 'worker', header=worker_header(), executions=executions), aws)

    def test_human_with_forged_worker_header_still_needs_team(self, route, aws):
        _assert_denied(_call(route, 'editor_b', header=worker_header()), aws)


class TestDeleteExecution:
    """Decision 8: deleting execution history needs Editor+; returns 204."""

    def test_executor_cannot_delete(self, aws):
        route = next(r for r in ROUTES if r[0] == 'delete_execution')
        _assert_denied(_call(route, 'executor_a'), aws)

    def test_editor_deletes_204(self, aws):
        resource, client = aws
        resource.return_value.Table.return_value.query.return_value = {'Items': []}
        client.return_value.list_objects_v2.return_value = {}
        route = next(r for r in ROUTES if r[0] == 'delete_execution')
        response = _call(route, 'editor_a')
        assert response['statusCode'] == 204
        assert response['body'] == ''


class TestDeleteLiveView:
    def test_204_with_empty_body(self, aws):
        route = next(r for r in ROUTES if r[0] == 'delete_live_view')
        response = _call(route, 'executor_a')
        assert response['statusCode'] == 204
        assert response['body'] == ''


class TestCallbacksForLocalRuns:
    """Decision 9: a human Executor+ of the owning team may call the runner callbacks."""

    @pytest.mark.parametrize('module', ['update_execution_status', 'update_execution_step_status',
                                        'create_runtime_variable', 'generate_execution_artifact_url',
                                        'confirm_artifact_upload', 'create_live_view'])
    def test_owner_executor_allowed(self, module, aws):
        route = next(r for r in ROUTES if r[0] == module)
        _assert_allowed(_call(route, 'executor_a'), aws)

    @pytest.mark.parametrize('module', ['update_execution_status', 'update_execution_step_status'])
    def test_viewer_denied(self, module, aws):
        route = next(r for r in ROUTES if r[0] == module)
        _assert_denied(_call(route, 'viewer_a'), aws)


class TestGetLiveViewMethodGuard:
    def test_options_answered_without_auth(self, aws):
        import get_live_view
        assert get_live_view.handler({'httpMethod': 'OPTIONS'}, None)['statusCode'] == 200

    def test_non_get_405(self, aws):
        import get_live_view
        assert get_live_view.handler({'httpMethod': 'POST'}, None)['statusCode'] == 405
