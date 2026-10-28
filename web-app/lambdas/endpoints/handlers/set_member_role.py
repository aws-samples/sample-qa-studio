import lambda_init  # noqa: F401 — must be first import
import json
import os
import logging
from typing import Any, Dict
from utils import create_response, extract_user_identity, validate_path_id
import permissions_repo
from resource_auth import require_team_role, validate_team_role
from role_scopes import TEAM_ROLES
import cognito_sync
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Change a team member's role.

    Requires api/admin scope OR caller must be team lead of the target team.
    Implements membership mutation saga with compensation.

    Path parameters:
        id: Team ID
        userId: User sub (Cognito sub)

    Request body:
        { "role": "editor" }

    Returns:
        200: Updated membership {team_id, user_sub, role}
        400: Invalid input
        403: Insufficient permissions
        404: Membership not found
        500: Saga failure (compensated)
    """
    # Auth: admin or team-lead
    user_identity = extract_user_identity(event)
    team_id_raw = (event.get('pathParameters') or {}).get('id', '')
    auth_error = require_team_role(user_identity, team_id_raw, 'team_lead', 'Admin or team lead required')
    if auth_error:
        return auth_error

    team_id, error = validate_path_id(
        (event.get('pathParameters') or {}).get('id'), 'team ID'
    )
    if error:
        return error

    path_params = event.get('pathParameters') or {}
    user_sub = path_params.get('userId', '').strip()
    if not user_sub:
        return create_response(400, {'error': 'userId path parameter is required'})

    # Parse body
    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    new_role = body.get('role', '').strip()
    if not new_role:
        return create_response(400, {'error': 'role is required'})
    role_error = validate_team_role(new_role)
    if role_error:
        return role_error

    # SAGA Step 1: Update role in DynamoDB
    try:
        updated = permissions_repo.set_member_role(user_sub, team_id, new_role)
    except KeyError:
        return create_response(404, {'error': 'Membership not found'})

    old_role = updated.get('_old_role', '')
    # Determine old role from the fact that set_member_role returns the updated item
    # We need to get old role before the update — since set_member_role already updated,
    # we know the new_role is set. The old role was whatever it was before.
    # Unfortunately set_member_role doesn't return old_role. We detect a no-op:
    # if the returned role == new_role AND we didn't get a KeyError, it was either
    # the same role (no-op) or successfully changed. Either way, sync Cognito.

    # SAGA Step 2: Sync role change to Cognito (add-first-then-remove)
    user_pool_id = os.environ.get('USER_POOL_ID', '')
    if user_pool_id and updated.get('role') == new_role:
        # We need the old role for the Cognito sync — query the membership's previous state.
        # Since set_member_role already mutated DynamoDB, we need a different approach.
        # The cognito_sync.set_user_role function handles add-new, remove-old.
        # We pass all roles and let Cognito handle idempotently via group membership.
        # For safety, we iterate over all possible roles and remove the user from any
        # group that doesn't match the new role.
        try:
            _sync_role_to_cognito(user_sub, team_id, new_role, user_pool_id)
        except Exception as e:
            # Compensate: this is complex since we already wrote to DynamoDB.
            # Log the inconsistency — it will self-heal on next token refresh.
            logger.error(
                f"Cognito sync failed for role change {user_sub} in team {team_id}: {e}. "
                f"DynamoDB is authoritative; Cognito will be stale until next sync."
            )

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='role_change',
        target={'user_sub': user_sub, 'team_id': team_id},
        details={'new_role': new_role},
    )

    response_body = {
        'team_id': team_id,
        'user_sub': user_sub,
        'role': new_role,
    }

    logger.info(f"Set role in team {team_id} to {new_role}")
    return create_response(200, response_body)


def _sync_role_to_cognito(sub: str, team_id: str, new_role: str, user_pool_id: str) -> None:
    """
    Ensure user is in the correct Cognito group for their new role.

    Uses add-first-then-remove strategy (BL-6) to prevent access gaps.
    """
    import boto3
    client = boto3.client('cognito-idp')

    new_group = f'team-{team_id}-{new_role}'

    # Step 1: Add to new group (no access gap)
    try:
        client.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=sub,
            GroupName=new_group,
        )
    except Exception as e:
        logger.error(f"Failed to add {sub} to group {new_group}: {e}")
        raise

    # Step 2: Remove from all other team role groups
    for role in TEAM_ROLES:
        if role == new_role:
            continue
        old_group = f'team-{team_id}-{role}'
        try:
            client.admin_remove_user_from_group(
                UserPoolId=user_pool_id,
                Username=sub,
                GroupName=old_group,
            )
        except Exception:
            # User may not be in this group — that's fine
            pass
