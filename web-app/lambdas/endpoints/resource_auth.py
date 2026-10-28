"""
Resource authorization decision engine.

Implements the 9-step authorize_resource algorithm (BL-2) with:
- Admin bypass (FR-1.3)
- Ceiling rule for shared access (FR-3.3)
- Creator-retains-edit override (FR-4.1, bounded by FR-4.3)
- Per-test-case override narrowing (FR-5.1, FR-5.2)
- Deny-by-default on any error

This is the second enforcement layer, called by mutation handlers after require_scopes.
"""

import lambda_init  # noqa: F401 — adds dependencies/ (pydantic) to sys.path
import functools
import hashlib
import hmac
import json
import logging
from typing import Callable, Optional

from pydantic import BaseModel

from utils import extract_user_identity, create_response, require_scopes, validate_path_id
from permissions_repo import (
    get_app_owner,
    get_app_ownership,
    get_usecase_owner,
    get_suite_owner,
    get_execution_record,
    get_suite_execution_record,
    list_shared_access,
    list_apps_shared_with_team,
    get_testcase_override,
    batch_get_testcase_overrides,
    list_user_teams,
    get_team,
)
from role_scopes import ROLE_RANK, ACCESS_RANK, TEAM_ROLES

logger = logging.getLogger()

# Sentinel distinguishing "owner not supplied" from a legitimate None owner
# (None means an orphaned app → deny). Callers that already hold the resource
# pass owner_team_id explicitly to avoid a redundant get_app_owner() read.
_UNSET = object()

# ---------------------------------------------------------------------------
# Permission Level Mappings
# ---------------------------------------------------------------------------

# Maps a team role to an effective permission level name. Admin is not a team
# role (studio admins bypass resource checks via is_admin instead).
_ROLE_TO_LEVEL = {
    'team_lead': 'full',
    'editor': 'full',
    'executor': 'execute',
    'viewer': 'view',
}

# Action requirements: minimum effective level needed to perform each action
_ACTION_REQUIRES = {
    'view': 'view',
    'execute': 'execute',
    'edit': 'full',
    'delete': 'full',
}


def _level_rank(level: str) -> int:
    """Return numeric rank for a permission level. Higher = more access."""
    return ACCESS_RANK.get(level, 0)


# ---------------------------------------------------------------------------
# Core Helpers
# ---------------------------------------------------------------------------


def effective_permission(caller_role: str, shared_level: str) -> str:
    """
    Compute effective permission using the ceiling rule (BL-3, FR-3.3).

    effective = min(role_to_level(caller_role), access_level(shared_level))

    Args:
        caller_role: The caller's role in their team (e.g. 'editor', 'viewer').
        shared_level: The shared access level granted (e.g. 'full', 'execute', 'view').

    Returns:
        Effective permission level string: 'full', 'execute', or 'view'.
    """
    role_level = _ROLE_TO_LEVEL.get(caller_role, 'view')
    role_rank = _level_rank(role_level)
    shared_rank = _level_rank(shared_level)

    effective_rank = min(role_rank, shared_rank)

    # Map rank back to level name
    for level, rank in sorted(ACCESS_RANK.items(), key=lambda x: x[1]):
        if rank == effective_rank:
            return level

    return 'view'  # Deny-by-default: lowest permission


def can_act(effective_level: str, action: str) -> bool:
    """
    Check if the effective permission level is sufficient for the action (BL-4).

    Args:
        effective_level: Computed effective permission ('full', 'execute', 'view').
        action: Requested action ('view', 'execute', 'edit', 'delete').

    Returns:
        True if action is allowed, False otherwise.
    """
    required_level = _ACTION_REQUIRES.get(action)
    if required_level is None:
        return False  # Unknown action → deny

    return _level_rank(effective_level) >= _level_rank(required_level)


# ---------------------------------------------------------------------------
# Team role checks (team management endpoints)
# ---------------------------------------------------------------------------


def is_studio_admin(identity: dict) -> bool:
    """Admin flag from the authorizer, or a token carrying the api/admin scope."""
    return bool(identity.get('is_admin')) or 'api/admin' in identity.get('scopes', [])


def has_team_role(identity: dict, team_id: Optional[str], min_role: str) -> bool:
    """
    Check whether the caller holds at least `min_role` in a team.

    Only roles in TEAM_ROLES count; anything else in team_roles is ignored
    (fail closed). Studio admins are NOT special-cased here; see require_team_role.

    Args:
        identity: Caller identity dict (from extract_user_identity).
        team_id: Team to check. None means "in any team".
        min_role: Minimum team role ('team_lead', 'editor', 'executor', 'viewer').

    Returns:
        True if the caller holds a team role ranked >= min_role in the team.
    """
    min_rank = ROLE_RANK[min_role]
    for tr in identity.get('team_roles', []):
        role = tr.get('role')
        if role not in TEAM_ROLES or ROLE_RANK[role] < min_rank:
            continue
        if team_id is None or tr.get('team_id') == team_id:
            return True
    return False


def require_team_role(identity: dict, team_id: Optional[str], min_role: str,
                      error_message: str = 'Admin or team lead required') -> Optional[dict]:
    """
    Allow studio admins, or callers holding at least `min_role` in `team_id`.

    Args:
        identity: Caller identity dict (from extract_user_identity).
        team_id: Team to check. None means "in any team".
        min_role: Minimum team role required.
        error_message: Message for the 403 response.

    Returns:
        None when allowed, otherwise a 403 response.
    """
    if is_studio_admin(identity) or has_team_role(identity, team_id, min_role):
        return None
    return create_response(403, {'error': error_message})


def require_owner_team_lead(identity: dict, owner_team_id: Optional[str]) -> Optional[dict]:
    """
    Allow studio admins, or a Team Lead of the resource's owning team.

    Shared access never satisfies this check (app metadata belongs to the
    owner team). An orphaned resource (owner None) is admin-only.

    Returns:
        None when allowed, otherwise a 403 response.
    """
    if is_studio_admin(identity):
        return None
    if owner_team_id and has_team_role(identity, owner_team_id, 'team_lead'):
        return None
    return create_response(403, {'error': 'Team lead of the owning team required'})


def require_oauth_client_manager(identity: dict, client_record: dict) -> Optional[dict]:
    """
    Allow the creator of an OAuth client, a Team Lead of the client's team,
    or a studio admin to delete / rotate it.

    Args:
        identity: Caller identity dict (from extract_user_identity).
        client_record: The OAUTH_CLIENTS/{client_id} item (created_by, team_id).

    Returns:
        None when allowed, otherwise a 403 response.
    """
    if is_studio_admin(identity):
        return None
    created_by = client_record.get('created_by')
    if created_by and created_by == identity.get('identity'):
        return None
    team_id = client_record.get('team_id')
    if team_id and has_team_role(identity, team_id, 'team_lead'):
        return None
    return create_response(403, {
        'error': 'Forbidden',
        'message': 'Only the creator, a team lead of the client team, or an admin can manage this OAuth client',
    })


def validate_team_role(role: str) -> Optional[dict]:
    """
    Validate a role assigned through a team endpoint.

    Admin is studio-wide and can only be granted via PATCH /users/{id}.

    Returns:
        None when `role` is a team role, otherwise a 400 response.
    """
    if role == 'admin':
        return create_response(400, {'error': 'Admin is studio-wide; use PATCH /users/{id}'})
    if role not in TEAM_ROLES:
        return create_response(400, {'error': f'Invalid role. Must be one of: {", ".join(TEAM_ROLES)}'})
    return None


# ---------------------------------------------------------------------------
# Main Authorization Function (BL-2)
# ---------------------------------------------------------------------------


def authorize_resource(event: dict, app_id: str, action: str, created_by: str = None,
                       owner_team_id=_UNSET):
    """
    Second enforcement layer — resource-level authorization.

    Implements the full 9-step algorithm from BL-2:
    1. Extract identity
    2. Admin → ALLOW
    3. Get app owner (None → DENY orphaned)
    4. Direct team membership check
    5. Shared access check (ceiling rule)
    6. No access path → DENY
    7. can_act check
    8. Creator-retains-edit override
    9. ALLOW

    Args:
        event: API Gateway proxy event (with identity from authorizer).
        app_id: The application ID being accessed.
        action: One of 'view', 'execute', 'edit', 'delete'.
        created_by: Optional sub of the resource creator (for creator-retains-edit).
            If None, the creator override is skipped.
        owner_team_id: Optional owning-team id. When supplied (callers that
            already loaded the resource/app), the internal get_app_owner() read
            is skipped — saving a DynamoDB round-trip. Pass None to signal an
            explicitly orphaned resource. Omit to let this function read it.

    Returns:
        Tuple of (identity_dict, error_response_or_None).
        On allow: (identity, None)
        On deny: (identity, error_response_dict)
    """
    identity = None
    try:
        # Step 1: Extract identity
        identity = extract_user_identity(event)

        # Step 2: Admin bypass (FR-1.3)
        if identity.get('is_admin', False):
            logger.info(f"admin_bypass: sub={identity.get('sub')} app={app_id} action={action}")
            return identity, None

        # Step 3: Resolve app owner. Use the caller-supplied value when present
        # (avoids a redundant read); otherwise look it up.
        if owner_team_id is _UNSET:
            owner_team_id = get_app_owner(app_id)
        if owner_team_id is None:
            # Orphaned app — deny for non-admins (BR-4)
            logger.warning(f"orphaned_app_deny: sub={identity.get('sub')} app={app_id}")
            return identity, create_response(403, {
                'error': 'Forbidden',
                'message': 'Application not accessible',
            })

        # Get caller's team membership info
        team_roles = identity.get('team_roles', [])
        caller_team_ids = {tr['team_id'] for tr in team_roles if 'team_id' in tr}

        effective_level = None

        # Step 4: Check direct team membership
        caller_role_in_owner_team = None
        for tr in team_roles:
            if tr.get('team_id') == owner_team_id:
                caller_role_in_owner_team = tr.get('role')
                break

        if caller_role_in_owner_team:
            # Direct member of the owner team
            effective_level = _ROLE_TO_LEVEL.get(caller_role_in_owner_team, 'view')
        else:
            # Step 5: Check shared access (ceiling rule)
            grants = list_shared_access(owner_team_id)
            matched_grant = None
            caller_role_in_target_team = None

            for grant in grants:
                target_team_id = grant.get('target_team_id')
                grant_app_id = grant.get('app_id')

                if grant_app_id == app_id and target_team_id in caller_team_ids:
                    # Found a matching grant — find caller's role in the target team
                    for tr in team_roles:
                        if tr.get('team_id') == target_team_id:
                            matched_grant = grant
                            caller_role_in_target_team = tr.get('role')
                            break
                    if matched_grant:
                        break

            if matched_grant and caller_role_in_target_team:
                shared_level = matched_grant.get('level', 'view')
                effective_level = effective_permission(caller_role_in_target_team, shared_level)
            else:
                # Step 6: No access path found
                logger.info(f"no_access_path: sub={identity.get('sub')} app={app_id}")
                return identity, create_response(403, {
                    'error': 'Forbidden',
                    'message': 'No access to this application',
                })

        # Step 7: Check action against effective permission
        if can_act(effective_level, action):
            # Step 9: ALLOW
            return identity, None

        # Step 8: Creator-retains-edit override (FR-4.1, bounded by FR-4.3)
        if action == 'edit' and created_by and not can_act(effective_level, 'edit'):
            # Creator override only grants 'edit' — NOT 'delete'
            caller_sub = identity.get('sub', '')

            # Condition 1: caller.sub == resource.created_by
            if caller_sub and caller_sub == created_by:
                # Condition 2 (FR-4.3): caller still has team membership
                has_team_membership = (
                    caller_role_in_owner_team is not None
                    or owner_team_id in caller_team_ids
                )

                if has_team_membership:
                    logger.info(
                        f"creator_override_granted: sub={caller_sub} app={app_id}"
                    )
                    return identity, None

        # Action not permitted
        logger.info(
            f"insufficient_permissions: sub={identity.get('sub')} app={app_id} "
            f"action={action} effective={effective_level}"
        )
        return identity, create_response(403, {
            'error': 'Forbidden',
            'message': 'Insufficient permissions for this action',
        })

    except Exception as e:
        # Deny-by-default: any exception results in a 500 deny
        logger.error(f"authorize_resource_error: {e}", exc_info=True)
        if identity is None:
            identity = {'sub': '', 'identity': 'unknown', 'identity_type': 'unknown'}
        return identity, create_response(500, {
            'error': 'Internal Server Error',
            'message': 'Authorization check failed',
        })


# ---------------------------------------------------------------------------
# Resource resolvers (H-2) — map a request to the resource's owner
# ---------------------------------------------------------------------------


class ResourceRef(BaseModel):
    """
    The resource a request targets, as resolved from its path/query/body.

    `owner_team_id=None` means orphaned (no application, or an app without an
    owner); authorize_resource denies that for everyone but admins. `error`
    short-circuits the request (400 for a bad id, 404 when not found).
    """
    app_id: Optional[str] = None
    owner_team_id: Optional[str] = None
    created_by: Optional[str] = None
    usecase_id: Optional[str] = None
    execution_id: Optional[str] = None
    suite_id: Optional[str] = None
    suite_execution_id: Optional[str] = None
    error: Optional[dict] = None


def _failed(response: dict) -> ResourceRef:
    return ResourceRef(error=response)


def _not_found(what: str) -> ResourceRef:
    return _failed(create_response(404, {'error': f'{what} not found'}))


def _path_param(event: dict, name: str, label: str):
    return validate_path_id((event.get('pathParameters') or {}).get(name), label)


def _json_body(event: dict) -> dict:
    try:
        body = json.loads(event.get('body') or '{}')
    except (TypeError, ValueError):
        return {}
    return body if isinstance(body, dict) else {}


def owner_of(record: dict) -> tuple:
    """
    (app_id, owner_team_id) of a use case / suite record. A record without an
    application_id is orphaned (owner None) even if it still carries a stale
    owner_team_id. The denormalized owner_team_id saves the app read.
    """
    app_id = record.get('application_id')
    if not app_id:
        return None, None
    return app_id, record.get('owner_team_id') or get_app_owner(app_id)


def _usecase_ref(usecase_id: str, action: str, **extra) -> ResourceRef:
    owner = get_usecase_owner(usecase_id, include_creator=(action == 'edit'))
    if owner is None:
        return _not_found('Use case')
    app_id, owner_team_id = owner_of(owner)
    return ResourceRef(app_id=app_id, owner_team_id=owner_team_id,
                       created_by=owner.get('created_by'), usecase_id=usecase_id, **extra)


def _suite_ref(suite_id: str, **extra) -> ResourceRef:
    owner = get_suite_owner(suite_id)
    if owner is None:
        return _not_found('Test suite')
    app_id, owner_team_id = owner_of(owner)
    return ResourceRef(app_id=app_id, owner_team_id=owner_team_id, suite_id=suite_id, **extra)


def usecase_from_path(event: dict, action: str = 'view') -> ResourceRef:
    """/usecase/{id}/... — the use case and its owning app."""
    usecase_id, err = _path_param(event, 'id', 'usecase ID')
    if err:
        return _failed(err)
    return _usecase_ref(usecase_id, action)


def execution_from_path(event: dict, action: str = 'view') -> ResourceRef:
    """
    /usecase/{id}/executions/{executionId}/... — the execution must exist
    under that use case (404 otherwise), so a foreign executionId can't be
    reached through a use case the caller owns.
    """
    usecase_id, err = _path_param(event, 'id', 'usecase ID')
    if err:
        return _failed(err)
    execution_id, err = _path_param(event, 'executionId', 'execution ID')
    if err:
        return _failed(err)
    execution = get_execution_record(usecase_id, execution_id)
    if execution is None:
        return _not_found('Execution')
    return _usecase_ref(usecase_id, action, execution_id=execution_id,
                        suite_id=execution.get('suite_id'),
                        suite_execution_id=execution.get('suite_execution_id'))


def suite_from_path(event: dict, action: str = 'view') -> ResourceRef:
    """/test-suites/{suite_id}/... — the suite and its owning app."""
    suite_id, err = _path_param(event, 'suite_id', 'suite ID')
    if err:
        return _failed(err)
    return _suite_ref(suite_id)


def suite_execution_from_path(event: dict, action: str = 'view') -> ResourceRef:
    """/test-suites/{suite_id}/executions/{execution_id}/... — must exist under the suite."""
    suite_id, err = _path_param(event, 'suite_id', 'suite ID')
    if err:
        return _failed(err)
    execution_id, err = _path_param(event, 'execution_id', 'execution ID')
    if err:
        return _failed(err)
    if get_suite_execution_record(suite_id, execution_id) is None:
        return _not_found('Suite execution')
    return _suite_ref(suite_id, suite_execution_id=execution_id)


def _app_ref(app_id: str) -> ResourceRef:
    ownership = get_app_ownership(app_id)
    if ownership is None:
        return _not_found('Application')
    return ResourceRef(app_id=app_id, owner_team_id=ownership['owner_team_id'])


def app_from_path(event: dict, action: str = 'view') -> ResourceRef:
    """/applications/{id}/... — the application itself."""
    app_id, err = _path_param(event, 'id', 'application ID')
    if err:
        return _failed(err)
    return _app_ref(app_id)


def usecase_from_body(field: str = 'usecaseId') -> Callable[..., ResourceRef]:
    """Resolver factory: an existing use case named by a JSON body field."""
    def resolver(event: dict, action: str = 'view') -> ResourceRef:
        usecase_id, err = validate_path_id(_json_body(event).get(field), field)
        if err:
            return _failed(err)
        return _usecase_ref(usecase_id, action)
    return resolver


def app_from_body(field: str = 'application_id') -> Callable[..., ResourceRef]:
    """Resolver factory: the target application of a create request (required)."""
    def resolver(event: dict, action: str = 'view') -> ResourceRef:
        app_id, err = validate_path_id(_json_body(event).get(field), field)
        if err:
            return _failed(err)
        return _app_ref(app_id)
    return resolver


def authorize_record(event: dict, record: dict, action: str) -> Optional[dict]:
    """
    authorize_resource for an already-loaded use case / suite record (its app
    and owner via owner_of; no application = orphaned, admins only).

    Returns:
        None when allowed, otherwise the error response.
    """
    app_id, owner_team_id = owner_of(record)
    _, err = authorize_resource(event, app_id or '', action, owner_team_id=owner_team_id)
    return err


def authorize_target_app(event: dict, app_id, action: str = 'edit') -> tuple:
    """
    Authorize `action` on a second application named by a request, e.g. the
    app a use case is moved to or cloned into (the decorator only covers the
    path resource).

    Returns:
        (owner_team_id, None) when allowed (owner None = orphaned app, admins
        only), otherwise (None, error response): 400 bad id, 404 unknown app,
        403 no access.
    """
    app_id, err = validate_path_id(app_id, 'application_id')
    if err:
        return None, err
    ref = _app_ref(app_id)
    if ref.error:
        return None, ref.error
    _, err = authorize_resource(event, app_id, action, owner_team_id=ref.owner_team_id)
    if err:
        return None, err
    return ref.owner_team_id, None


def new_usecase_owner_fields(app_id: str) -> dict:
    """
    application_id + owner_team_id to stamp on a use case created under
    `app_id` (the decorator already checked edit on that app). The
    denormalized owner is omitted when the app has none (orphan, admin only).
    """
    fields = {'application_id': app_id}
    owner_team_id = get_app_owner(app_id)
    if owner_team_id:
        fields['owner_team_id'] = owner_team_id
    return fields


def _session_ref(usecase_id: str, session_id: str, action: str) -> ResourceRef:
    """A wizard / recording session is an execution of its use case; it must exist under it."""
    if get_execution_record(usecase_id, session_id) is None:
        return _not_found('Wizard session')
    return _usecase_ref(usecase_id, action, execution_id=session_id)


def wizard_session_from_path(event: dict, action: str = 'view') -> ResourceRef:
    """
    /wizard/{sessionId}/... — a wizard session is an execution of its use
    case. usecaseId comes from the path, else the query string, else the body;
    the session must exist under that use case.
    """
    session_id, err = _path_param(event, 'sessionId', 'session ID')
    if err:
        return _failed(err)
    usecase_id = ((event.get('pathParameters') or {}).get('usecaseId')
                  or (event.get('queryStringParameters') or {}).get('usecaseId')
                  or _json_body(event).get('usecaseId'))
    usecase_id, err = validate_path_id(usecase_id, 'usecase ID')
    if err:
        return _failed(err)
    return _session_ref(usecase_id, session_id, action)


def authorize_session(event: dict, usecase_id, session_id, action: str = 'edit') -> Optional[dict]:
    """
    Authorize `action` on a wizard / recording session named outside the
    path (e.g. the session prefix of a screenshot manifest key).

    Returns:
        None when allowed, otherwise the error response: 400 bad id, 404 when
        the session doesn't exist under the use case, 403 no access.
    """
    usecase_id, err = validate_path_id(usecase_id, 'usecase ID')
    if err:
        return err
    session_id, err = validate_path_id(session_id, 'session ID')
    if err:
        return err
    ref = _session_ref(usecase_id, session_id, action)
    if ref.error:
        return ref.error
    _, err = authorize_resource(event, ref.app_id or '', action, created_by=ref.created_by,
                                owner_team_id=ref.owner_team_id)
    return err


# ---------------------------------------------------------------------------
# Worker capability (H-2) — the worker may only touch its own execution
# ---------------------------------------------------------------------------


# HTTP header NAME carrying the worker capability, not a secret value.
EXECUTION_TOKEN_HEADER = 'x-qa-execution-token'  # nosec B105  # nosemgrep
_WORKER_ACTIVE_STATUSES = frozenset({'pending', 'running'})


def _header(event: dict, name: str) -> Optional[str]:
    """Case-insensitive request header lookup."""
    for key, value in (event.get('headers') or {}).items():
        if key.lower() == name:
            return value
    return None


def parse_execution_token(raw: Optional[str]) -> Optional[tuple]:
    """
    Parse an X-QA-Execution-Token value '{usecase_id}:{execution_id}:{token}'.

    Returns:
        (usecase_id, execution_id, token), or None when malformed.
    """
    parts = (raw or '').split(':', 2)
    if len(parts) != 3 or not parts[2]:
        return None
    usecase_id, execution_id, token = parts
    for value in (usecase_id, execution_id):
        if validate_path_id(value)[1]:
            return None
    return usecase_id, execution_id, token


def _authorize_worker(event: dict, ref: ResourceRef) -> Optional[dict]:
    """
    Authorize the shared worker client through its execution capability.

    The worker presents '{usecase_id}:{execution_id}:{token}'. Allowed only
    when the token's sha256 matches worker_token_hash on that execution, the
    execution is still pending/running, and the request targets that same
    execution: same use case, same executionId when the path has one, and the
    execution's suite_id / suite_execution_id for suite routes.

    Returns:
        None when allowed, otherwise a 403 response.
    """
    deny = create_response(403, {'error': 'Forbidden', 'message': 'Worker capability required'})
    parsed = parse_execution_token(_header(event, EXECUTION_TOKEN_HEADER))
    if parsed is None:
        return deny
    usecase_id, execution_id, token = parsed

    if ref.usecase_id is None and ref.suite_id is None:
        return deny  # not an execution-scoped resource
    if ref.usecase_id is not None and ref.usecase_id != usecase_id:
        return deny
    if ref.execution_id is not None and ref.execution_id != execution_id:
        return deny

    execution = get_execution_record(usecase_id, execution_id)
    if execution is None:
        return deny
    stored_hash = execution.get('worker_token_hash') or ''
    presented_hash = hashlib.sha256(token.encode()).hexdigest()
    if not stored_hash or not hmac.compare_digest(stored_hash, presented_hash):
        logger.warning(f"worker_token_mismatch: usecase={usecase_id} execution={execution_id}")
        return deny
    if execution.get('status') not in _WORKER_ACTIVE_STATUSES:
        logger.info(f"worker_execution_not_active: execution={execution_id} status={execution.get('status')}")
        return deny
    if ref.suite_id is not None and execution.get('suite_id') != ref.suite_id:
        return deny
    if ref.suite_execution_id is not None and execution.get('suite_execution_id') != ref.suite_execution_id:
        return deny
    return None


# ---------------------------------------------------------------------------
# Handler decorator — the single resource enforcement point (DRY)
# ---------------------------------------------------------------------------


def _hidden_by_override(identity: dict, action: str, ref: ResourceRef) -> bool:
    """
    'view' of a use case resource (the use case itself or anything under it,
    e.g. its executions) also honours the per-test-case override (BR-3). The
    worker is bound to its execution by the capability token, so overrides
    (which narrow human visibility) don't apply to it.
    """
    if action != 'view' or not ref.usecase_id or identity.get('identity_type') == 'worker':
        return False
    return not can_view_testcase(identity, ref.usecase_id, _owner_team_role(identity, ref.owner_team_id))


def require_resource_access(action: str, resolver, *, scopes: list, allow_worker: bool = False):
    """
    Decorator that enforces scope and resource-level authorization before a
    handler runs.

    Order: require_scopes(scopes) → resolver (400/404 short-circuit) →
    worker capability (only when allow_worker) or authorize_resource on the
    resolved owner → per-test-case override on 'view' of use case resources
    (404 when hidden). Orphaned resources (owner None) are denied for
    non-admins. Any resolver error fails closed with a 500.

    Args:
        action: One of 'view', 'execute', 'edit', 'delete'.
        resolver: Callable(event, action) -> ResourceRef.
        scopes: OAuth scopes the token must carry.
        allow_worker: Let the worker client through via its execution capability.

    Returns:
        The wrapped handler, or an error response when access is denied.
    """
    def decorator(handler):
        @functools.wraps(handler)
        def wrapper(event, *args, **kwargs):
            identity, scope_err = require_scopes(event, scopes)
            if scope_err:
                return scope_err

            try:
                ref = resolver(event, action)
            except Exception as e:
                logger.error(f"resource_resolver_error: {type(e).__name__}", exc_info=True)
                return create_response(500, {
                    'error': 'Internal Server Error',
                    'message': 'Authorization check failed',
                })
            if ref.error:
                return ref.error

            if identity.get('identity_type') == 'worker':
                if not allow_worker:
                    return create_response(403, {
                        'error': 'Forbidden',
                        'message': 'Worker access not allowed on this route',
                    })
                auth_err = _authorize_worker(event, ref)
            else:
                _, auth_err = authorize_resource(
                    event,
                    ref.app_id or '',
                    action,
                    created_by=ref.created_by,
                    owner_team_id=ref.owner_team_id,
                )
            if auth_err:
                return auth_err
            if _hidden_by_override(identity, action, ref):
                # 404, not 403: don't reveal that a hidden test case exists
                return create_response(404, {'error': 'Use case not found'})
            return handler(event, *args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# List Filtering (BL-5)
# ---------------------------------------------------------------------------


def annotate_app_source(identity: dict, app: dict, owner_team_id: str) -> dict:
    """
    Annotate an app with source metadata for the current user.

    Adds 'source', 'sharedFrom', and 'effectiveLevel' fields.

    Args:
        identity: Caller identity dict (from extract_user_identity).
        app: Application dict to annotate.
        owner_team_id: The app's owner team ID.

    Returns:
        Annotated app dict (mutated in-place and returned).
    """
    team_roles = identity.get('team_roles', [])
    caller_team_ids = {tr['team_id'] for tr in team_roles if 'team_id' in tr}

    if owner_team_id in caller_team_ids:
        app['source'] = 'owned'
        # Find caller's role in the owner team
        for tr in team_roles:
            if tr.get('team_id') == owner_team_id:
                app['effectiveLevel'] = _ROLE_TO_LEVEL.get(tr.get('role'), 'view')
                break
    else:
        app['source'] = 'shared'
        # Find the grant and compute effective level
        try:
            grants = list_shared_access(owner_team_id)
            app_id = app.get('id') or app.get('app_id', '')
            for grant in grants:
                target_team_id = grant.get('target_team_id')
                if grant.get('app_id') == app_id and target_team_id in caller_team_ids:
                    for tr in team_roles:
                        if tr.get('team_id') == target_team_id:
                            shared_level = grant.get('level', 'view')
                            app['effectiveLevel'] = effective_permission(tr.get('role'), shared_level)
                            break
                    # Try to get the owner team name
                    owner_team = get_team(owner_team_id)
                    app['sharedFrom'] = owner_team.get('name', owner_team_id) if owner_team else owner_team_id
                    break
        except Exception:
            app['sharedFrom'] = owner_team_id
            app['effectiveLevel'] = 'view'

    return app


def filter_visible_apps(identity: dict, apps: list) -> list:
    """
    Filter and annotate applications based on caller's access (BL-5).

    Args:
        identity: Caller identity dict.
        apps: List of application dicts (each must have 'owner_team_id').

    Returns:
        Filtered list of apps the caller can see, annotated with source info.
    """
    # Admin sees everything
    if identity.get('is_admin', False):
        for app in apps:
            app['source'] = 'owned'
            app['effectiveLevel'] = 'full'
        return apps

    team_roles = identity.get('team_roles', [])
    caller_team_ids = {tr['team_id'] for tr in team_roles if 'team_id' in tr}

    if not caller_team_ids:
        return []

    visible = []

    # Build a lookup of incoming shares for all caller's teams
    incoming_grants = {}
    for team_id in caller_team_ids:
        try:
            grants = list_apps_shared_with_team(team_id)
            for grant in grants:
                grant_app_id = grant.get('app_id', '')
                if grant_app_id:
                    incoming_grants.setdefault(grant_app_id, []).append(grant)
        except Exception:
            pass

    for app in apps:
        owner_team_id = app.get('owner_team_id')

        # Skip orphaned apps for non-admins (BR-4)
        if not owner_team_id:
            continue

        # Direct ownership
        if owner_team_id in caller_team_ids:
            annotate_app_source(identity, app, owner_team_id)
            visible.append(app)
            continue

        # Shared access
        app_id = app.get('id') or app.get('app_id', '')
        if app_id in incoming_grants:
            annotate_app_source(identity, app, owner_team_id)
            visible.append(app)
            continue

    return visible


# ---------------------------------------------------------------------------
# Per-Test-Case Override (BR-3)
# ---------------------------------------------------------------------------


def _owner_team_role(identity: dict, owner_team_id: Optional[str]) -> Optional[str]:
    """The caller's role in the owning team (None for share-only callers)."""
    if not owner_team_id:
        return None
    return next((tr.get('role') for tr in identity.get('team_roles', [])
                 if tr.get('team_id') == owner_team_id), None)


def _override_allows(identity: dict, override: Optional[dict], caller_role: Optional[str]) -> bool:
    """
    Whether a per-test-case override lets the caller see the test case (BR-3).
    No override = standard permissions apply. Overrides only narrow:
    allowed_subs restricts to those subs, allowed_roles to those owner-team
    roles; both must pass when both are set.
    """
    if override is None:
        return True
    allowed_subs = override.get('allowed_subs', [])
    if allowed_subs and identity.get('sub', '') not in allowed_subs:
        return False
    allowed_roles = override.get('allowed_roles', [])
    if allowed_roles and caller_role not in allowed_roles:
        return False
    return True


def can_view_testcase(identity: dict, testcase_id: str, caller_role: Optional[str]) -> bool:
    """
    Check if a per-test-case override narrows visibility for this caller (BR-3).

    Overrides can only NARROW access — they cannot grant more than team membership provides.
    Admin bypasses overrides (FR-1.3).

    Args:
        identity: Caller identity dict.
        testcase_id: The test case ID to check.
        caller_role: The caller's role in the owning team (None if share-only).

    Returns:
        True if the caller can view the test case, False if override denies visibility.
    """
    if is_studio_admin(identity):
        return True
    try:
        override = get_testcase_override(testcase_id)
    except Exception:
        # On error, deny (deny-by-default)
        logger.warning(f"testcase_override_lookup_failed: testcase={testcase_id}")
        return False
    return _override_allows(identity, override, caller_role)


def can_view_testcase_batch(identity: dict, owner_by_testcase: dict) -> set:
    """
    Batch form of can_view_testcase for list endpoints: one BatchGetItem on
    USECASE#{id}/OVERRIDE per 100 test cases instead of a read per item.

    Args:
        identity: Caller identity dict.
        owner_by_testcase: {testcase_id: owner_team_id}; the caller's role in
            that owner team is what allowed_roles is matched against.

    Returns:
        The visible test case ids. Admins see all; on a lookup error nothing
        is visible (deny by default).
    """
    if is_studio_admin(identity):
        return set(owner_by_testcase)
    if not owner_by_testcase:
        return set()
    try:
        overrides = batch_get_testcase_overrides(list(owner_by_testcase))
    except Exception:
        logger.warning(f"testcase_override_batch_failed: count={len(owner_by_testcase)}")
        return set()
    return {tc for tc, owner_team_id in owner_by_testcase.items()
            if _override_allows(identity, overrides.get(tc), _owner_team_role(identity, owner_team_id))}
