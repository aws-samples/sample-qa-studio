import lambda_init  # noqa: F401 — must be first import
import json
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, require_scopes, aws_error_code
import permissions_repo
import cognito_sync
from role_scopes import TEAM_ROLES
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 'admin' means the studio-wide 'admins' group; anything else is a team role.
_VALID_ROLES = ('admin',) + TEAM_ROLES


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a user's team assignment.

    Requires api/admin scope.

    Path parameters:
        userId: Cognito user sub

    Request body:
        { "teamId": "...", "role": "editor" }

    Returns:
        200: Updated user {userId, teamId, role}
        400: Invalid input
        403: Insufficient permissions
        409: Demoting the last member of the global 'admins' group
        500: Last-admin check failed (fail closed)
    """
    user_identity, error_response = require_scopes(event, ['api/admin'])
    if error_response:
        return error_response

    path_params = event.get('pathParameters') or {}
    user_sub = path_params.get('userId', '').strip()
    if not user_sub:
        return create_response(400, {'error': 'userId path parameter is required'})

    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    team_id = body.get('teamId', '').strip()
    role = body.get('role', '').strip()

    if not role:
        return create_response(400, {'error': 'role is required'})
    if role not in _VALID_ROLES:
        return create_response(400, {'error': f'Invalid role. Must be one of: {", ".join(_VALID_ROLES)}'})

    user_pool_id = os.environ.get('USER_POOL_ID', '')

    # Admin is teamless: remove all team memberships/groups and add the global
    # 'admins' group. Ignore any team selection.
    if role == 'admin':
        existing_teams = permissions_repo.list_user_teams(user_sub)
        client = boto3.client('cognito-idp') if user_pool_id else None
        for old in existing_teams:
            old_team_id = old.get('team_id', '')
            old_role = old.get('role', '')
            if not old_team_id:
                continue
            try:
                permissions_repo.remove_membership(user_sub, old_team_id)
            except Exception as e:
                logger.warning(f"Failed to remove membership {old_team_id}: {e}")
            if client:
                try:
                    client.admin_remove_user_from_group(
                        UserPoolId=user_pool_id, Username=user_sub,
                        GroupName=f'team-{old_team_id}-{old_role}')
                except Exception as e:
                    logger.warning(f"Failed to remove old group: {e}")
        if client:
            try:
                client.admin_add_user_to_group(
                    UserPoolId=user_pool_id, Username=user_sub, GroupName='admins')
            except Exception as e:
                logger.warning(f"Failed to add to 'admins' group: {e}")
        actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
        log_permission_change(actor=actor, action='user_update',
                              target={'user_sub': user_sub}, details={'role': 'admin'})
        return create_response(200, {'userId': user_sub, 'role': 'admin'})

    if not team_id:
        return create_response(400, {'error': 'teamId is required'})

    # Verify team exists
    team = permissions_repo.get_team(team_id)
    if not team:
        return create_response(404, {'error': 'Team not found'})

    # Last-admin guard (global 'admins' group): never demote the only admin.
    # Fail closed if the check itself fails.
    if user_pool_id:
        try:
            if cognito_sync.is_last_studio_admin(user_sub, user_pool_id):
                return create_response(409, {'error': 'Cannot demote the last admin'})
        except Exception as e:
            logger.error(f"Last-admin check failed: {aws_error_code(e)}")
            return create_response(500, {'error': 'Failed to verify admin membership'})

    # Check if user already has a membership in this team
    existing_teams = permissions_repo.list_user_teams(user_sub)
    existing_membership = None
    for m in existing_teams:
        if m.get('team_id') == team_id:
            existing_membership = m
            break

    # Demotion from admin → team role: drop the global 'admins' group if present
    if user_pool_id:
        try:
            boto3.client('cognito-idp').admin_remove_user_from_group(
                UserPoolId=user_pool_id, Username=user_sub, GroupName='admins')
        except Exception:
            pass  # not in admins group — fine

    if existing_membership:
        # Update role in existing team
        old_role = existing_membership.get('role', '')
        if old_role == role:
            return create_response(200, {'userId': user_sub, 'teamId': team_id, 'role': role})

        permissions_repo.set_member_role(user_sub, team_id, role)

        # Sync Cognito groups
        if user_pool_id:
            try:
                cognito_sync.set_user_role(user_sub, team_id, old_role, role, user_pool_id)
            except Exception as e:
                logger.warning(f"Cognito sync failed for role change: {e}")
    else:
        # Moving to a new team — remove all existing memberships first so the
        # user ends up in exactly one team (one-team-per-user model).
        client = boto3.client('cognito-idp') if user_pool_id else None
        for old in existing_teams:
            old_team_id = old.get('team_id', '')
            old_role = old.get('role', '')
            if not old_team_id:
                continue
            try:
                permissions_repo.remove_membership(user_sub, old_team_id)
            except Exception as e:
                logger.warning(f"Failed to remove old membership {old_team_id}: {e}")
            if client:
                try:
                    client.admin_remove_user_from_group(
                        UserPoolId=user_pool_id,
                        Username=user_sub,
                        GroupName=f'team-{old_team_id}-{old_role}',
                    )
                except Exception as e:
                    logger.warning(f"Failed to remove user from old group: {e}")

        # Add membership to new team
        permissions_repo.add_membership(team_id, user_sub, role)

        # Add to Cognito group
        if client:
            try:
                client.admin_add_user_to_group(
                    UserPoolId=user_pool_id,
                    Username=user_sub,
                    GroupName=f'team-{team_id}-{role}',
                )
            except Exception as e:
                logger.warning(f"Cognito sync failed: {e}")

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='user_update',
        target={'user_sub': user_sub},
        details={'team_id': team_id, 'role': role},
    )

    logger.info(f"Updated user: team={team_id}, role={role}")
    return create_response(200, {'userId': user_sub, 'teamId': team_id, 'role': role})
