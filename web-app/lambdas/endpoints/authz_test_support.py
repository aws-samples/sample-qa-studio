"""
Shared helpers for handler tests of resource-protected routes (H-2).

Not a test module (pytest only collects test_*.py). Builds API Gateway
events for the caller kinds the cross-team tests need and patches the
resource_auth owner readers so handlers can be exercised without DynamoDB.

Fixture layout:
- use case UC_ID and suite SUITE_ID belong to app APP_ID owned by TEAM_A
- execution EXEC_ID exists under UC_ID; suite execution SUITE_EXEC_ID under SUITE_ID
- TEAM_B owns nothing; shares are opt-in via `shares=`
"""

import contextlib
import hashlib
import json
from unittest.mock import patch

TEAM_A = 'team-a'
TEAM_B = 'team-b'
APP_ID = 'app-a'
UC_ID = 'uc-a'
EXEC_ID = 'ex-a'
SUITE_ID = 'suite-a'
SUITE_EXEC_ID = 'sx-a'
WORKER_TOKEN = 'worker-token-a'
WORKER_TOKEN_HASH = hashlib.sha256(WORKER_TOKEN.encode()).hexdigest()

# All scopes a team role can carry (scope checks are covered per handler;
# these callers exist to exercise the resource check).
ALL_SCOPES = ' '.join([
    'api/usecases.read', 'api/usecases.write', 'api/usecases.execute',
    'api/executions.read', 'api/executions.write',
    'api/suite.read', 'api/suite.write',
    'api/templates.read', 'api/templates.write',
    'api/applications.read', 'api/applications.write',
])

# Caller kind -> (identityType, teamRoles, isAdmin)
CALLERS = {
    'viewer_a': ('user', [{'team_id': TEAM_A, 'role': 'viewer'}], False),
    'executor_a': ('user', [{'team_id': TEAM_A, 'role': 'executor'}], False),
    'editor_a': ('user', [{'team_id': TEAM_A, 'role': 'editor'}], False),
    'lead_a': ('user', [{'team_id': TEAM_A, 'role': 'team_lead'}], False),
    'viewer_b': ('user', [{'team_id': TEAM_B, 'role': 'viewer'}], False),
    'executor_b': ('user', [{'team_id': TEAM_B, 'role': 'executor'}], False),
    'editor_b': ('user', [{'team_id': TEAM_B, 'role': 'editor'}], False),
    'lead_b': ('user', [{'team_id': TEAM_B, 'role': 'team_lead'}], False),
    'admin': ('user', [], True),
    'no_team': ('user', [], False),
    'client_a': ('client', [{'team_id': TEAM_A, 'role': 'editor'}], False),
    'client_b': ('client', [{'team_id': TEAM_B, 'role': 'editor'}], False),
    'client_unbound': ('client', [], False),
    'worker': ('worker', [], False),
}


def make_event(caller='editor_a', path=None, body=None, query=None, scopes=ALL_SCOPES,
               headers=None, worker_header=None, sub='caller-sub'):
    """
    API Gateway proxy event for `caller` (a CALLERS key).

    worker_header: '{usecase_id}:{execution_id}:{token}' sent as X-QA-Execution-Token.
    """
    identity_type, team_roles, is_admin = CALLERS[caller]
    authorizer = {
        'sub': sub,
        'identityType': identity_type,
        'teamRoles': json.dumps(team_roles),
        'isAdmin': 'true' if is_admin else 'false',
        'scope': scopes,
    }
    if identity_type == 'user':
        authorizer['email'] = f'{caller}@example.com'
    else:
        authorizer['clientId'] = f'{caller}-client'
    all_headers = dict(headers or {})
    if worker_header is not None:
        all_headers['X-QA-Execution-Token'] = worker_header
    return {
        'pathParameters': path or {},
        'queryStringParameters': query,
        'headers': all_headers,
        'body': json.dumps(body) if body is not None and not isinstance(body, str) else body,
        'requestContext': {'authorizer': authorizer},
    }


def worker_header(usecase_id=UC_ID, execution_id=EXEC_ID, token=WORKER_TOKEN):
    return f'{usecase_id}:{execution_id}:{token}'


def execution_record(status='running', token_hash=WORKER_TOKEN_HASH, suite_id=None,
                     suite_execution_id=None):
    return {'status': status, 'worker_token_hash': token_hash,
            'suite_id': suite_id, 'suite_execution_id': suite_execution_id}


@contextlib.contextmanager
def owned_resources(usecase_app=APP_ID, suite_app=APP_ID, owner_team=TEAM_A, shares=None,
                    executions=None, suite_executions=None, usecases=None, created_by=None,
                    overrides=None):
    """
    Patch the resource_auth owner readers.

    Args:
        usecase_app / suite_app: application_id of UC_ID / SUITE_ID ('' = orphan).
        owner_team: owner team of APP_ID.
        shares: grants returned by list_shared_access, e.g.
            [{'app_id': APP_ID, 'target_team_id': TEAM_B, 'level': 'execute'}].
        executions: {(usecase_id, execution_id): record}; defaults to EXEC_ID under UC_ID.
        suite_executions: {(suite_id, execution_id): record}; defaults to SUITE_EXEC_ID.
        usecases: extra {usecase_id: owner dict} beyond UC_ID.
        created_by: creator sub of UC_ID (creator-retains-edit).
        overrides: {usecase_id: per-test-case override} (default: none).
    """
    usecase_owners = {UC_ID: {'application_id': usecase_app, 'owner_team_id': owner_team if usecase_app else None,
                              'created_by': created_by}}
    usecase_owners.update(usecases or {})
    suite_owners = {SUITE_ID: {'application_id': suite_app, 'owner_team_id': owner_team if suite_app else None}}
    executions = executions if executions is not None else {(UC_ID, EXEC_ID): execution_record()}
    suite_executions = (suite_executions if suite_executions is not None
                        else {(SUITE_ID, SUITE_EXEC_ID): {'status': 'running'}})

    def usecase_owner(usecase_id, include_creator=False):
        return usecase_owners.get(usecase_id)

    def app_ownership(app_id):
        return {'owner_team_id': owner_team} if app_id == APP_ID else None

    with patch('resource_auth.get_usecase_owner', side_effect=usecase_owner), \
            patch('resource_auth.get_suite_owner', side_effect=lambda s: suite_owners.get(s)), \
            patch('resource_auth.get_execution_record', side_effect=lambda u, e: executions.get((u, e))), \
            patch('resource_auth.get_suite_execution_record',
                  side_effect=lambda s, e: suite_executions.get((s, e))), \
            patch('resource_auth.get_app_ownership', side_effect=app_ownership), \
            patch('resource_auth.get_app_owner', side_effect=lambda a: owner_team if a == APP_ID else None), \
            patch('resource_auth.list_shared_access', return_value=list(shares or [])), \
            patch('resource_auth.get_testcase_override', side_effect=lambda u: (overrides or {}).get(u)), \
            patch('resource_auth.batch_get_testcase_overrides',
                  side_effect=lambda ids: {u: (overrides or {})[u] for u in ids if u in (overrides or {})}):
        yield


@contextlib.contextmanager
def owned_everything(owner_team=TEAM_A):
    """
    Every use case / suite / (suite) execution id resolves to APP_ID owned by
    `owner_team`. For tests of handler logic that don't care which ids they use.
    """
    owner = {'application_id': APP_ID, 'owner_team_id': owner_team, 'created_by': None}
    with patch('resource_auth.get_usecase_owner', return_value=dict(owner)), \
            patch('resource_auth.get_suite_owner', return_value=dict(owner)), \
            patch('resource_auth.get_execution_record', return_value=execution_record()), \
            patch('resource_auth.get_suite_execution_record', return_value={'status': 'running'}), \
            patch('resource_auth.get_app_ownership', return_value={'owner_team_id': owner_team}), \
            patch('resource_auth.get_app_owner', return_value=owner_team), \
            patch('resource_auth.list_shared_access', return_value=[]), \
            patch('resource_auth.get_testcase_override', return_value=None), \
            patch('resource_auth.batch_get_testcase_overrides', return_value={}):
        yield


@contextlib.contextmanager
def resource_access_granted():
    """
    Owner lookups resolve and authorize_resource allows (scopes are still
    checked). For handler-logic tests whose events don't model team
    membership; the access rules themselves are covered by the *_access tests.
    """
    with owned_everything(), patch('resource_auth.authorize_resource', return_value=({}, None)):
        yield


def as_caller(event, caller='editor_a', scopes=None):
    """
    Return `event` with its authorizer context replaced by `caller`'s.
    Keeps the event's own scope string unless `scopes` is given.
    """
    old = (event.get('requestContext') or {}).get('authorizer') or {}
    scope = scopes if scopes is not None else (old.get('scope') or ALL_SCOPES)
    new = make_event(caller, scopes=scope)['requestContext']
    return {**event, 'requestContext': {**(event.get('requestContext') or {}), **new}}


def share(level, target_team=TEAM_B, app_id=APP_ID):
    """A shared-access grant of APP_ID to `target_team` at `level`."""
    return [{'app_id': app_id, 'target_team_id': target_team, 'level': level}]
