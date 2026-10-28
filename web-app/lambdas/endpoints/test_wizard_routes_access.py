"""
Cross-team access for the wizard and generate_* routes (H-2, Appendix A
rows /import, /generate-usecase, /generate-s3-url, /wizard/...).

- Wizard session routes need edit on the session's use case; the session must
  exist under it (usecaseId from the path, the query, or the JSON body).
- /wizard/start, /import and /templates/{id}/apply create a use case, so they
  need a body application_id with edit on that app (N-4); the new use case is
  stamped with application_id / owner_team_id.
- /generate-s3-url: uploads need api/usecases.write + edit, downloads need
  api/executions.read + view (N-2); the use case update never upserts.
- /generate-usecase: a screenshot manifest key must be the manifest of a
  recording session the caller can edit.
"""
import importlib
import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from authz_test_support import (
    ALL_SCOPES, APP_ID, EXEC_ID, TEAM_A, UC_ID, make_event, owned_resources, share, worker_header,
)

SESSION_ID = EXEC_ID  # a wizard session is an execution of its use case

# (module, path params, query, body)
SESSION_ROUTES = [
    ('add_wizard_step', {'sessionId': SESSION_ID}, None,
     {'usecaseId': UC_ID, 'instruction': 'click', 'step_type': 'action'}),
    ('accept_wizard_step', {'sessionId': SESSION_ID, 'stepId': 's1', 'usecaseId': UC_ID}, None, {}),
    ('reject_wizard_step', {'sessionId': SESSION_ID, 'stepId': 's1', 'usecaseId': UC_ID}, None, {}),
    ('restart_wizard', {'sessionId': SESSION_ID}, None, {'usecaseId': UC_ID}),
    ('terminate_wizard_session', {'sessionId': SESSION_ID, 'usecaseId': UC_ID}, None, {}),
    ('send_recording_command', {'sessionId': SESSION_ID}, None,
     {'usecaseId': UC_ID, 'action': 'recording_start'}),
    ('get_recording_data', {'sessionId': SESSION_ID}, {'usecaseId': UC_ID}, None),
]
SESSION_IDS = [r[0] for r in SESSION_ROUTES]

# Routes that create a use case under a body application_id: (module, path, body, scopes)
CREATE_ROUTES = [
    ('start_wizard_session', {}, {'name': 'w', 'starting_url': 'https://example.test'},
     ['api/usecases.write']),
    ('import_usecase', {}, {'exportVersion': '1.0', 'usecase': {'name': 'i'}, 'steps': []},
     ['api/usecases.write']),
    ('apply_template', {'id': 'tpl-1'}, {'name': 't'}, ['api/templates.read', 'api/usecases.write']),
]
CREATE_IDS = [r[0] for r in CREATE_ROUTES]

MODULE_CLIENTS = {
    'terminate_wizard_session': ('dynamodb', 'sqs', 'eventbridge'),
    'restart_wizard': ('sqs', 'eventbridge'),
    'send_recording_command': ('eventbridge',),
    'start_wizard_session': ('dynamodb', 'ecs'),
    'generate_usecase': ('bedrock_runtime',),
}


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    """boto3 fully mocked; module-level clients replaced too."""
    for name, value in {'TABLE_NAME': 't', 'SECRET_PREFIX': 'p', 'BUCKET_NAME': 'b', 'S3_BUCKET': 'b',
                        'WIZARD_EVENT_BUS_NAME': 'bus', 'WIZARD_QUEUE_URL': 'q', 'ECS_CLUSTER': 'c',
                        'ECS_TASK_DEFINITION': 'td', 'SUBNET_ID': 'sn', 'SECURITY_GROUP_ID': 'sg',
                        'BEDROCK_EXECUTION_ROLE': 'r', 'NOVA_ACT_API_KEY_NAME': 'k',
                        'BEDROCK_MODEL_ID': 'm'}.items():
        monkeypatch.setenv(name, value)
    resource, client = MagicMock(name='resource'), MagicMock(name='client')
    for module, attrs in MODULE_CLIENTS.items():
        mod = importlib.import_module(module)
        for attr in attrs:
            monkeypatch.setattr(mod, attr, client)
    with patch('boto3.resource', resource), patch('boto3.client', client):
        yield resource, client


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


def _run(module, event, **owned):
    handler = importlib.import_module(module).handler
    with owned_resources(**owned):
        try:
            return handler(event, None)
        except Exception as exc:  # noqa: BLE001 — a crash on mocked AWS data is past authorization
            return {'statusCode': None, 'raised': repr(exc)}


# ---------------------------------------------------------------------------
# Wizard session routes: edit on the session's use case
# ---------------------------------------------------------------------------


def _session_call(route, caller, scopes=ALL_SCOPES, header=None, **owned):
    module, path, query, body = route
    event = make_event(caller, path=dict(path), query=query, body=body, scopes=scopes,
                       worker_header=header)
    return _run(module, event, **owned)


@pytest.mark.parametrize('route', SESSION_ROUTES, ids=SESSION_IDS)
class TestWizardSessionRouteAccess:
    def test_owner_editor_allowed(self, route, aws):
        _assert_allowed(_session_call(route, 'editor_a'), aws)

    @pytest.mark.parametrize('caller', ['executor_a', 'viewer_a', 'no_team'])
    def test_below_editor_denied(self, route, aws, caller):
        _assert_denied(_session_call(route, caller), aws)

    def test_other_team_editor_denied(self, route, aws):
        _assert_denied(_session_call(route, 'editor_b'), aws)

    def test_shared_full_allowed(self, route, aws):
        _assert_allowed(_session_call(route, 'editor_b', shares=share('full')), aws)

    def test_shared_execute_denied(self, route, aws):
        _assert_denied(_session_call(route, 'editor_b', shares=share('execute')), aws)

    def test_orphan_usecase_admin_only(self, route, aws):
        _assert_denied(_session_call(route, 'editor_a', usecase_app=''), aws)
        _assert_allowed(_session_call(route, 'admin', usecase_app=''), aws)

    def test_session_not_under_usecase_404(self, route, aws):
        _assert_denied(_session_call(route, 'admin', executions={}), aws, status=404)

    def test_bound_client_allowed(self, route, aws):
        _assert_allowed(_session_call(route, 'client_a'), aws)

    @pytest.mark.parametrize('caller', ['client_unbound', 'client_b'])
    def test_unbound_or_foreign_client_denied(self, route, aws, caller):
        _assert_denied(_session_call(route, caller), aws)

    def test_worker_denied_even_with_capability(self, route, aws):
        _assert_denied(_session_call(route, 'worker', header=worker_header(execution_id=SESSION_ID)), aws)

    def test_missing_write_scope_denied(self, route, aws):
        scopes = ' '.join(s for s in ALL_SCOPES.split() if s != 'api/usecases.write')
        _assert_denied(_session_call(route, 'editor_a', scopes=scopes), aws)

    def test_missing_usecase_id_400(self, route, aws):
        module, path, query, body = route
        path = {k: v for k, v in path.items() if k != 'usecaseId'}
        body = {k: v for k, v in (body or {}).items() if k != 'usecaseId'} if body is not None else None
        response = _run(module, make_event('admin', path=path, query=None, body=body))
        _assert_denied(response, aws, status=400)


class TestWizardSessionBinding:
    def test_body_usecase_other_team_cannot_reach_session(self, aws):
        """A session id paired with a use case the caller can't edit is denied."""
        other_uc = {'uc-b': {'application_id': 'app-b', 'owner_team_id': 'team-b', 'created_by': None}}
        event = make_event('editor_a', path={'sessionId': SESSION_ID}, body={'usecaseId': 'uc-b'})
        response = _run('restart_wizard', event, usecases=other_uc,
                        executions={('uc-b', SESSION_ID): {'status': 'running'}})
        _assert_denied(response, aws)

    def test_accept_writes_step_into_path_usecase(self, aws):
        table = aws[0].return_value.Table.return_value
        table.get_item.return_value = {'Item': {'instruction': 'i', 'step_type': 'action'}}
        table.query.return_value = {'Items': []}
        event = make_event('editor_a', path={'sessionId': SESSION_ID, 'stepId': 's1', 'usecaseId': UC_ID})
        response = _run('accept_wizard_step', event)
        assert response['statusCode'] == 200
        assert table.put_item.call_args.kwargs['Item']['pk'] == f'USECASE#{UC_ID}'

    def test_restart_non_object_body_400(self, aws):
        event = make_event('admin', path={'sessionId': SESSION_ID}, body='[1]')
        _assert_denied(_run('restart_wizard', event), aws, status=400)

    def test_command_body_requires_action(self, aws):
        event = make_event('editor_a', path={'sessionId': SESSION_ID}, body={'usecaseId': UC_ID})
        response = _run('send_recording_command', event)
        assert response['statusCode'] == 400


# ---------------------------------------------------------------------------
# Use case creators: application_id required + edit on it (N-4)
# ---------------------------------------------------------------------------


def _create_call(route, caller, application_id=APP_ID, scopes=None, **owned):
    module, path, body, route_scopes = route
    body = dict(body)
    if application_id is not None:
        body['application_id'] = application_id
    event = make_event(caller, path=dict(path), body=body,
                       scopes=scopes if scopes is not None else ALL_SCOPES)
    return _run(module, event, **owned)


def _stored_usecase(route, aws):
    """The USECASES item the handler wrote (plain dict)."""
    resource, client = aws
    if route[0] == 'start_wizard_session':
        for call in client.put_item.call_args_list:
            item = call.kwargs['Item']
            if item['pk']['S'] == 'USECASES':
                return {k: v.get('S') for k, v in item.items()}
        return None
    table = resource.return_value.Table.return_value
    for call in table.put_item.call_args_list:
        if call.kwargs['Item'].get('pk') == 'USECASES':
            return call.kwargs['Item']
    return None


@pytest.mark.parametrize('route', CREATE_ROUTES, ids=CREATE_IDS)
class TestUsecaseCreatorAccess:
    @pytest.fixture(autouse=True)
    def _template(self, aws):
        table = aws[0].return_value.Table.return_value
        table.get_item.return_value = {'Item': {'pk': 'TEMPLATES', 'sk': 'TEMPLATE#tpl-1'}}
        table.query.return_value = {'Items': []}

    def test_owner_editor_creates_owned_usecase(self, route, aws):
        response = _create_call(route, 'editor_a')
        assert response['statusCode'] in (200, 201), response
        item = _stored_usecase(route, aws)
        assert item['application_id'] == APP_ID
        assert item['owner_team_id'] == TEAM_A

    @pytest.mark.parametrize('application_id', [None, ''])
    def test_missing_application_id_400(self, route, aws, application_id):
        _assert_denied(_create_call(route, 'editor_a', application_id=application_id), aws, status=400)

    def test_unknown_application_404(self, route, aws):
        _assert_denied(_create_call(route, 'admin', application_id='app-missing'), aws, status=404)

    @pytest.mark.parametrize('caller', ['executor_a', 'viewer_a', 'editor_b', 'client_unbound', 'worker'])
    def test_without_edit_on_app_denied(self, route, aws, caller):
        _assert_denied(_create_call(route, caller), aws)

    def test_shared_full_allowed(self, route, aws):
        response = _create_call(route, 'editor_b', shares=share('full'))
        assert response['statusCode'] in (200, 201), response

    def test_bound_client_allowed(self, route, aws):
        response = _create_call(route, 'client_a')
        assert response['statusCode'] in (200, 201), response

    def test_missing_route_scope_denied(self, route, aws):
        for scope in route[3]:
            scopes = ' '.join(s for s in ALL_SCOPES.split() if s != scope)
            _assert_denied(_create_call(route, 'editor_a', scopes=scopes), aws)

    def test_orphan_app_owner_not_stamped_for_admin(self, route, aws):
        response = _create_call(route, 'admin', owner_team=None)
        assert response['statusCode'] in (200, 201), response
        item = _stored_usecase(route, aws)
        assert item['application_id'] == APP_ID
        assert 'owner_team_id' not in item


def test_import_ignores_application_fields_inside_export(aws):
    """Ownership comes from the body application_id only, never from the export file."""
    body = {'exportVersion': '1.0', 'application_id': APP_ID, 'steps': [],
            'usecase': {'name': 'i', 'application_id': 'app-b', 'owner_team_id': 'team-b'}}
    response = _run('import_usecase', make_event('editor_a', body=body))
    assert response['statusCode'] == 200
    item = _stored_usecase(CREATE_ROUTES[1], aws)
    assert (item['application_id'], item['owner_team_id']) == (APP_ID, TEAM_A)


# ---------------------------------------------------------------------------
# /generate-s3-url (N-2)
# ---------------------------------------------------------------------------

UPLOADS = [
    {'fileType': 'app_binary', 'usecaseId': UC_ID, 'platform': 'ANDROID', 'filename': 'a.apk'},
    {'fileType': 'browser_policy', 'usecaseId': UC_ID, 'filename': 'p.json'},
]
DOWNLOADS = [
    {'fileType': 'html', 'usecaseId': UC_ID, 'executionId': EXEC_ID, 'actId': 'a1'},
    {'fileType': 'video', 'usecaseId': UC_ID, 'executionId': EXEC_ID},
]


def _s3_url(caller, body, scopes=ALL_SCOPES, **owned):
    return _run('generate_s3_url', make_event(caller, body=body, scopes=scopes), **owned)


@pytest.mark.parametrize('body', UPLOADS, ids=lambda b: b['fileType'])
class TestGenerateS3UrlUpload:
    def test_owner_editor_allowed_with_condition(self, body, aws):
        client = aws[1]
        client.return_value.generate_presigned_url.return_value = 'https://signed'
        response = _s3_url('editor_a', body)
        assert response['statusCode'] == 200, response
        update = aws[0].return_value.Table.return_value.update_item.call_args.kwargs
        assert update['ConditionExpression'] == 'attribute_exists(pk)'
        assert update['Key'] == {'pk': 'USECASES', 'sk': f'USECASE#{UC_ID}'}

    @pytest.mark.parametrize('caller', ['executor_a', 'viewer_a', 'editor_b', 'client_unbound', 'worker'])
    def test_without_edit_denied(self, body, aws, caller):
        _assert_denied(_s3_url(caller, body), aws)

    def test_missing_write_scope_denied(self, body, aws):
        scopes = ' '.join(s for s in ALL_SCOPES.split() if s != 'api/usecases.write')
        _assert_denied(_s3_url('editor_a', body, scopes=scopes), aws)

    def test_orphan_usecase_admin_only(self, body, aws):
        _assert_denied(_s3_url('editor_a', body, usecase_app=''), aws)

    def test_unknown_usecase_404(self, body, aws):
        _assert_denied(_s3_url('admin', {**body, 'usecaseId': 'uc-missing'}), aws, status=404)

    def test_missing_usecase_id_400(self, body, aws):
        _assert_denied(_s3_url('admin', {k: v for k, v in body.items() if k != 'usecaseId'}), aws, status=400)

    def test_record_vanished_no_upsert_404(self, body, aws):
        table = aws[0].return_value.Table.return_value
        table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'x'}}, 'UpdateItem')
        response = _s3_url('editor_a', body)
        assert response['statusCode'] == 404


@pytest.mark.parametrize('body', DOWNLOADS, ids=lambda b: b['fileType'])
class TestGenerateS3UrlDownload:
    @pytest.mark.parametrize('caller', ['viewer_a', 'executor_a', 'editor_a', 'client_a', 'admin'])
    def test_view_allowed(self, body, aws, caller):
        _assert_allowed(_s3_url(caller, body), aws)

    def test_shared_view_allowed(self, body, aws):
        _assert_allowed(_s3_url('viewer_b', body, shares=share('view')), aws)

    @pytest.mark.parametrize('caller', ['no_team', 'editor_b', 'client_unbound', 'worker'])
    def test_without_view_denied(self, body, aws, caller):
        _assert_denied(_s3_url(caller, body), aws)

    def test_missing_executions_read_denied(self, body, aws):
        scopes = ' '.join(s for s in ALL_SCOPES.split() if s != 'api/executions.read')
        _assert_denied(_s3_url('editor_a', body, scopes=scopes), aws)

    def test_write_scope_alone_is_not_enough(self, body, aws):
        _assert_denied(_s3_url('editor_a', body, scopes='api/usecases.write'), aws)


def test_generate_s3_url_invalid_file_type_400(aws):
    _assert_denied(_s3_url('editor_a', {'fileType': 'exe', 'usecaseId': UC_ID}), aws, status=400)


def test_generate_s3_url_invalid_json_400(aws):
    _assert_denied(_s3_url('editor_a', '{not json'), aws, status=400)


# ---------------------------------------------------------------------------
# /generate-usecase: screenshot manifest restricted to the caller's session
# ---------------------------------------------------------------------------

MANIFEST_KEY = f'{UC_ID}/{SESSION_ID}/screenshot_manifest.json'


def _recording(manifest_key):
    return {
        'type': 'cdp_actions',
        'version': '1.0',
        'captured_at': '2026-01-01T00:00:00Z',
        'screenshot_manifest_key': manifest_key,
        'data': {
            'session': {'id': 'r1', 'startedAt': 1, 'stoppedAt': 2, 'tabId': 1,
                        'startingUrl': 'https://example.test',
                        'actions': [{'id': 'a1', 'type': 'click', 'prompt': 'Click', 'url': 'https://example.test',
                                     'timestamp': 1}]},
            'event_count': 1,
        },
    }


def _generate(caller, manifest_key, **owned):
    body = {'title': 'Journey', 'starting_url': 'https://example.test', 'region': 'us-east-1',
            'recording_data': _recording(manifest_key)}
    with patch('generate_usecase.invoke_bedrock', side_effect=RuntimeError('stop after auth')):
        return _run('generate_usecase', make_event(caller, body=body), **owned)


class TestGenerateUsecaseManifest:
    @pytest.mark.parametrize('key', [
        'screenshot_manifest.json',
        f'{UC_ID}/screenshot_manifest.json',
        f'{UC_ID}/{SESSION_ID}/other.json',
        f'{UC_ID}/{SESSION_ID}/x/screenshot_manifest.json',
        f'../{SESSION_ID}/screenshot_manifest.json',
    ])
    def test_malformed_key_400(self, aws, key):
        _assert_denied(_generate('editor_a', key), aws, status=400)

    @pytest.mark.parametrize('caller', ['editor_b', 'executor_a', 'viewer_a', 'client_unbound'])
    def test_session_of_another_caller_403(self, aws, caller):
        _assert_denied(_generate(caller, MANIFEST_KEY), aws)

    def test_session_not_under_usecase_404(self, aws):
        _assert_denied(_generate('editor_a', MANIFEST_KEY, executions={}), aws, status=404)

    def test_own_session_reads_manifest(self, aws):
        s3 = aws[1].return_value
        s3.get_object.return_value = {'Body': MagicMock(read=MagicMock(return_value=json.dumps({
            'a1': f'{UC_ID}/{SESSION_ID}/screenshots/a1.jpg',
        }).encode()))}
        response = _generate('editor_a', MANIFEST_KEY)
        assert response['statusCode'] == 502  # Bedrock stub raised after authorization
        s3.get_object.assert_any_call(Bucket='b', Key=MANIFEST_KEY)

    def test_manifest_entries_outside_session_prefix_dropped(self, aws):
        import generate_usecase
        prefix = f'{UC_ID}/{SESSION_ID}/screenshots/'
        manifest = {
            'a1': f'{prefix}a1.jpg',
            'a2': 'uc-b/sess-b/screenshots/a2.jpg',
            'a3': f'{prefix}../../uc-b/x.jpg',
            'a4': 7,
        }
        assert generate_usecase._manifest_within_prefix(manifest, prefix) == {'a1': f'{prefix}a1.jpg'}
        assert generate_usecase._manifest_within_prefix(['x'], prefix) == {}

    def test_foreign_screenshot_keys_never_fetched(self, aws):
        s3 = aws[1].return_value
        s3.get_object.return_value = {'Body': MagicMock(read=MagicMock(return_value=json.dumps({
            'a1': 'uc-b/sess-b/screenshots/a1.jpg',
        }).encode()))}
        with patch('generate_usecase._fetch_and_compress_screenshots', return_value=[]) as fetch:
            _generate('editor_a', MANIFEST_KEY)
        assert fetch.call_args.args[2] == {}

    def test_no_manifest_needs_no_session(self, aws):
        body = {'title': 'Journey', 'starting_url': 'https://example.test', 'region': 'us-east-1',
                'userJourney': 'Open the login page, enter the user name and password, submit the form and check the dashboard'}
        with patch('generate_usecase.invoke_bedrock', side_effect=RuntimeError('stop')):
            response = _run('generate_usecase', make_event('editor_b', body=body))
        assert response['statusCode'] == 502
