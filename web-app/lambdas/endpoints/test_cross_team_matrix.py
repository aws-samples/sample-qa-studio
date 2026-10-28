"""
Cross-team authorization matrix for every routed handler (H-2, Appendix A).

One table: each routed handler x each identity -> allowed or denied.

Identities: owner-team viewer / executor / editor / team lead, other-team
editor, other-team editor through a share at view / execute / full, studio
admin, M2M client bound to the owner team, unbound client, and the worker
holding a capability for an active execution of the owner's use case.

Allowed means past authorization (no 401/403; a 404 must come from the
handler, i.e. after AWS was read). Denied means 401/403 before the handler
touched AWS (for the two OAuth client routes, which must read the client
record to find its team: before anything was written).

The per-domain *_routes_access tests cover the finer cases (orphans, wrong
execution, missing scopes, finished executions); their route tables are
reused here so a route is declared once.
"""
import importlib
import signal
from unittest.mock import MagicMock, patch

import pytest

from authz_test_support import (
    ALL_SCOPES, APP_ID, EXEC_ID, SUITE_EXEC_ID, SUITE_ID, TEAM_A, UC_ID,
    execution_record, make_event, owned_resources, share, worker_header,
)
from test_execution_routes_access import ROUTES as EXECUTION_ROUTES
from test_suite_routes_access import ROUTES as SUITE_ROUTES
from test_usecase_routes_access import ROUTES as USECASE_ROUTES
from test_wizard_routes_access import CREATE_ROUTES as WIZARD_CREATE_ROUTES
from test_wizard_routes_access import SESSION_ROUTES as WIZARD_SESSION_ROUTES

EXTRA_SCOPES = 'api/oauth-clients.read api/oauth-clients.write'
ADMIN_SCOPES = f'{ALL_SCOPES} {EXTRA_SCOPES} api/admin api/teams.manage'

# identity -> (CALLERS key, shares granted to team-b, scopes)
IDENTITIES = {
    'owner_viewer': ('viewer_a', None, f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'owner_executor': ('executor_a', None, f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'owner_editor': ('editor_a', None, f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'owner_lead': ('lead_a', None, f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'other_editor': ('editor_b', None, f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'shared_view': ('editor_b', 'view', f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'shared_execute': ('editor_b', 'execute', f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'shared_full': ('editor_b', 'full', f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'admin': ('admin', None, ADMIN_SCOPES),
    'bound_client': ('client_a', None, f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'unbound_client': ('client_unbound', None, f'{ALL_SCOPES} {EXTRA_SCOPES}'),
    'worker': ('worker', None, f'{ALL_SCOPES} {EXTRA_SCOPES}'),
}
IDENTITY_IDS = list(IDENTITIES)

# Who passes each rule. The worker is handled per route (allow_worker).
OWNER = {'owner_viewer', 'owner_executor', 'owner_editor', 'owner_lead', 'bound_client', 'admin'}
RULES = {
    'view': OWNER | {'shared_view', 'shared_execute', 'shared_full'},
    'execute': (OWNER - {'owner_viewer'}) | {'shared_execute', 'shared_full'},
    'edit': {'owner_editor', 'owner_lead', 'bound_client', 'admin', 'shared_full'},
    # H-3: app metadata belongs to the owner team; shares never count
    'owner_team_lead': {'owner_lead', 'admin'},
    # team routes (path team = owner team)
    'team_member': {'owner_viewer', 'owner_executor', 'owner_editor', 'owner_lead', 'bound_client', 'admin'},
    'team_lead': {'owner_lead', 'admin'},
    'team_editor': {'owner_editor', 'owner_lead', 'bound_client', 'admin'},
    'oauth_client_manager': {'owner_lead', 'admin'},
    'admin': {'admin'},
    # global routes: the route scope is the only check (lists filter per item)
    'scope_only': set(IDENTITIES),
}
RULES['delete'] = RULES['edit']

UC_PATH = {'id': UC_ID}
EX_PATH = {'id': UC_ID, 'executionId': EXEC_ID}
SUITE_PATH = {'suite_id': SUITE_ID}
SX_PATH = {'suite_id': SUITE_ID, 'execution_id': SUITE_EXEC_ID}
APP_PATH = {'id': APP_ID}
TEAM_PATH = {'id': TEAM_A}


def _route(module, rule, path=None, body=None, query=None, worker=False, reads_first=False):
    return {'module': module, 'rule': rule, 'path': path or {}, 'body': body, 'query': query,
            'worker': worker, 'reads_first': reads_first or module in READS_FIRST}


# Routes whose effective rule is stricter than the path action: cloning needs
# view on the source and edit on the target app (the source's app by default).
EFFECTIVE_RULE = {'clone_usecase': 'edit'}
# Second checks that need the loaded record (reads allowed, writes not):
# clone reads the source before checking the target app; app update / delete
# read the app before the owner-team-lead check.
READS_FIRST = {'clone_usecase', 'handlers.update_application', 'handlers.delete_application'}


def _resource_routes():
    routes = []
    for module, action, worker, _scope, extra, body in USECASE_ROUTES:
        routes.append(_route(module, EFFECTIVE_RULE.get(module, action), {**UC_PATH, **extra}, body, worker=worker))
    for module, action, worker, _scope, extra, body in EXECUTION_ROUTES:
        path = UC_PATH if extra is None else {**EX_PATH, **extra}
        routes.append(_route(module, action, path, body, worker=worker))
    for module, action, worker, _scope, kind, extra, body in SUITE_ROUTES:
        base = SX_PATH if kind == 'sx' else SUITE_PATH
        routes.append(_route(module, action, {**base, **extra}, body, worker=worker))
    for module, path, query, body in WIZARD_SESSION_ROUTES:
        routes.append(_route(module, 'edit', path, body, query))
    for module, path, body, _scopes in WIZARD_CREATE_ROUTES:
        routes.append(_route(module, 'edit', path, {**body, 'application_id': APP_ID}))
    routes += [
        _route('execute_usecase', 'execute', UC_PATH, query={'trigger-type': 'ci_runner'}),
        _route('create_usecase', 'edit', body={'name': 'n', 'application_id': APP_ID}),
        _route('create_test_suite', 'edit', body={'name': 'n', 'application_id': APP_ID}),
        _route('generate_s3_url', 'edit',
               body={'fileType': 'browser_policy', 'usecaseId': UC_ID, 'filename': 'p.json'}),
        _route('generate_s3_url', 'view',
               body={'fileType': 'video', 'usecaseId': UC_ID, 'executionId': EXEC_ID}),
        _route('handlers.get_application', 'view', APP_PATH),
        _route('handlers.get_application_metrics', 'view', APP_PATH),
        _route('handlers.get_application_failures', 'view', APP_PATH),
        _route('handlers.get_application_flaky', 'view', APP_PATH),
        _route('handlers.update_application', 'owner_team_lead', APP_PATH, {'name': 'n'}),
        _route('handlers.delete_application', 'owner_team_lead', APP_PATH),
        _route('handlers.associate_usecases', 'edit', APP_PATH, {'usecase_ids': [UC_ID]}),
        _route('handlers.remove_usecase_association', 'edit', {**APP_PATH, 'usecaseId': UC_ID}),
    ]
    return routes


def _global_routes():
    tpl = {'id': 'tpl-1'}
    return [
        # filtered lists and global catalogues: scope only
        _route('list_usecases', 'scope_only'),
        _route('list_test_suites', 'scope_only'),
        _route('handlers.list_applications', 'scope_only'),
        _route('handlers.get_dashboard_overview', 'scope_only'),
        _route('list_models', 'scope_only'),
        _route('list_device_farm_devices', 'scope_only'),
        _route('list_scopes', 'scope_only'),
        _route('list_oauth_clients', 'scope_only'),
        _route('generate_usecase', 'scope_only',
               body={'title': 'T', 'starting_url': 'https://example.test', 'region': 'us-east-1',
                     'userJourney': 'Open the login page, enter the user name and password, submit and check'}),
        # templates are studio-global (decision 4)
        _route('list_templates', 'scope_only'),
        _route('create_template', 'scope_only', body={'name': 't'}),
        _route('get_template', 'scope_only', tpl),
        _route('update_template', 'scope_only', tpl, {'name': 't'}),
        _route('delete_template', 'scope_only', tpl),
        _route('list_template_steps', 'scope_only', tpl),
        _route('create_template_step', 'scope_only', tpl, {'instruction': 'i', 'step_type': 'action'}),
        _route('reorder_template_steps', 'scope_only', tpl, {'step_orders': []}),
        _route('update_template_step', 'scope_only', {**tpl, 'stepId': 's1'}, {'instruction': 'i'}),
        _route('delete_template_step', 'scope_only', {**tpl, 'stepId': 's1'}),
        _route('get_template_variables', 'scope_only', tpl),
        _route('create_template_variables', 'scope_only', tpl, {'variables': []}),
        # teams: the path team is the owner team
        _route('handlers.list_teams', 'team_lead'),
        _route('handlers.get_team', 'team_member', TEAM_PATH),
        _route('handlers.list_team_applications', 'team_member', TEAM_PATH),
        _route('handlers.list_team_members', 'team_lead', TEAM_PATH),
        _route('handlers.add_team_member', 'team_lead', TEAM_PATH, {'userId': 'u-1', 'role': 'viewer'}),
        _route('handlers.set_member_role', 'team_lead', {**TEAM_PATH, 'userId': 'u-1'}, {'role': 'viewer'}),
        _route('handlers.remove_team_member', 'team_lead', {**TEAM_PATH, 'userId': 'u-1'}),
        _route('handlers.list_shared_access', 'team_lead', TEAM_PATH),
        _route('handlers.grant_shared_access', 'team_lead', TEAM_PATH,
               {'targetTeamId': 'team-b', 'appId': APP_ID, 'level': 'view'}),
        _route('handlers.revoke_shared_access', 'team_lead', {**TEAM_PATH, 'grantId': 'g-1'}),
        _route('handlers.create_application', 'team_lead',
               body={'name': 'a', 'base_url': 'https://a.test', 'teamId': TEAM_A}),
        # OAuth clients are bound to a team (H-2)
        _route('create_oauth_client', 'team_editor',
               body={'name': 'ci', 'teamId': TEAM_A, 'scopes': ['api/usecases.execute']}),
        _route('delete_oauth_client', 'oauth_client_manager', {'clientId': 'c-1'}, reads_first=True),
        _route('rotate_client_secret', 'oauth_client_manager', {'clientId': 'c-1'}, reads_first=True),
        # studio admin only
        _route('handlers.create_team', 'admin', body={'name': 'New team'}),
        _route('handlers.update_team', 'admin', TEAM_PATH, {'name': 'Renamed'}),
        _route('handlers.delete_team', 'admin', TEAM_PATH),
        _route('handlers.reassign_application', 'admin', APP_PATH, {'teamId': TEAM_A}),
        _route('handlers.list_users', 'admin'),
        _route('handlers.create_user', 'admin', body={'email': 'new@example.com', 'role': 'viewer'}),
        _route('handlers.update_user', 'admin', {'userId': 'u-1'}, {'role': 'viewer'}),
        _route('get_user', 'admin', {'username': 'u-1'}),
        _route('delete_user', 'admin', {'username': 'u-1'}),
        _route('update_user_groups', 'admin', {'username': 'u-1'}, {'groups': ['users']}),
    ]


ALL_ROUTES = _resource_routes() + _global_routes()

# Import every handler up front, outside any boto3 patch, so module-level
# clients are real botocore objects that _mock_module_clients can swap.
for _module in {r['module'] for r in ALL_ROUTES}:
    importlib.import_module(_module)


def _route_id(route):
    rule = route['rule']
    detail = route['body'].get('fileType') if route['module'] == 'generate_s3_url' else None
    return f"{route['module']}[{detail or rule}]"


ENV = {
    'TABLE_NAME': 't', 'DYNAMODB_TABLE_NAME': 't', 'SECRET_PREFIX': 'p', 'BUCKET_NAME': 'b', 'S3_BUCKET': 'b',
    'USER_POOL_ID': 'pool', 'SCHEDULER_GROUP_NAME': 'g', 'EXECUTE_USECASE_LAMBDA_ARN': 'arn:x',
    'EXECUTE_SUITE_LAMBDA_ARN': 'arn:x', 'SCHEDULER_TARGET_ROLE_ARN': 'arn:r', 'SNS_TOPIC_ARN': 'arn:sns',
    'EVENT_BUS_NAME': 'bus', 'WIZARD_EVENT_BUS_NAME': 'bus', 'WIZARD_QUEUE_URL': 'q', 'ECS_CLUSTER': 'c',
    'ECS_TASK_DEFINITION': 'td', 'SUBNET_ID': 'sn', 'SECURITY_GROUP_ID': 'sg', 'BEDROCK_EXECUTION_ROLE': 'r',
    'NOVA_ACT_API_KEY_NAME': 'k', 'BEDROCK_MODEL_ID': 'm', 'RESOURCE_SERVER_IDENTIFIER': 'api',
}

# The worker's execution of UC_ID also belongs to the suite execution in the path.
WORKER_EXECUTIONS = {(UC_ID, EXEC_ID): execution_record(suite_id=SUITE_ID, suite_execution_id=SUITE_EXEC_ID)}

_WRITE_MARKERS = ('.delete', '.create', '.put_', '.update', '.admin_', '.transact', '.send', '.run_task')


def _mock_module_clients(monkeypatch, module, client):
    """Replace module-level boto3 clients / resources created at import time."""
    for name, value in list(vars(module).items()):
        if type(value).__module__.startswith(('botocore.client', 'boto3.resources')):
            monkeypatch.setattr(module, name, client)


class _AwsMock(MagicMock):
    """
    MagicMock whose responses read like empty AWS responses: response.get(k)
    returns the default, so pagination / UnprocessedKeys loops in handlers
    terminate instead of spinning on a truthy mock.
    """

    def get(self, key, default=None):
        return default


class _HandlerTimeout(Exception):
    pass


@pytest.fixture
def aws(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    resource, client = _AwsMock(name='resource'), _AwsMock(name='client')
    # Records the handlers read belong to team-a's app; the OAuth client is
    # bound to team-a and was created by someone else.
    resource.return_value.Table.return_value.get_item.return_value = {'Item': {
        'id': UC_ID, 'name': 'n', 'application_id': APP_ID, 'owner_team_id': TEAM_A,
        'team_id': TEAM_A, 'created_by': 'someone-else', 'total_usecases': 0}}
    with patch('boto3.resource', resource), patch('boto3.client', client):
        yield monkeypatch, resource, client


def _invoke(route, identity, aws):
    monkeypatch, _, client = aws
    module = importlib.import_module(route['module'])
    _mock_module_clients(monkeypatch, module, client)
    caller, share_level, scopes = IDENTITIES[identity]
    header = worker_header() if identity == 'worker' else None
    event = make_event(caller, path=dict(route['path']), query=route['query'], body=route['body'],
                       scopes=scopes, worker_header=header)
    event['httpMethod'] = 'GET'
    def _timeout(*_):
        raise _HandlerTimeout('handler still running after 5 s')

    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(5)
    with owned_resources(shares=share(share_level) if share_level else None, executions=WORKER_EXECUTIONS), \
            patch('permissions_repo.list_apps_shared_with_team', return_value=[]), \
            patch('time.sleep'):
        try:
            if hasattr(module, 'handle'):
                return module.handle(event)
            return module.handler(event, None)
        except Exception as exc:  # noqa: BLE001 — a crash on mocked AWS data is past authorization
            return {'statusCode': None, 'raised': repr(exc)}
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)


def _expected_allowed(route, identity):
    if identity == 'worker' and route['rule'] in ('view', 'execute', 'edit', 'delete'):
        return route['worker']
    return identity in RULES[route['rule']]


@pytest.mark.parametrize('identity', IDENTITY_IDS)
@pytest.mark.parametrize('route', ALL_ROUTES, ids=[_route_id(r) for r in ALL_ROUTES])
def test_cross_team_matrix(route, identity, aws):
    _, resource, client = aws
    response = _invoke(route, identity, aws)
    status = response['statusCode']
    if _expected_allowed(route, identity):
        assert status not in (401, 403), f'{identity} should pass: {response}'
        if status == 404:
            assert resource.mock_calls or client.mock_calls, f'404 before reading AWS: {response}'
    else:
        assert status in (401, 403), f'{identity} should be denied: {response}'
        calls = resource.mock_calls + client.mock_calls
        if route['reads_first']:
            writes = [c for c in calls if any(m in str(c) for m in _WRITE_MARKERS)]
            assert not writes, f'wrote before denying: {writes}'
        else:
            assert not calls, f'touched AWS before denying: {calls}'


def test_every_resource_rule_is_known():
    assert {r['rule'] for r in ALL_ROUTES} <= set(RULES)


def test_matrix_covers_every_routed_handler():
    """Every handler reachable through API Gateway has a row here."""
    from test_route_coverage import routed_handler_modules
    missing = routed_handler_modules() - {r['module'] for r in ALL_ROUTES}
    assert not missing, f'routed handlers without a cross-team matrix row: {sorted(missing)}'
