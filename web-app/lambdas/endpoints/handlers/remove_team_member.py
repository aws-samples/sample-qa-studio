import lambda_init  # noqa: F401 — must be first import
import os
import logging
from typing import Any, Dict
from utils import create_response, extract_user_identity, validate_path_id
import permissions_repo
from resource_auth import require_team_role
import cognito_sync
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove a member from a team.

    Requires api/admin scope OR caller must be team lead of the target team.

    Path parameters:
        id: Team ID
        userId: User sub (Cognito sub)

    Returns:
        204: Member removed
        403: Insufficient permissions
        404: Membership not found
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

    # Find the membership to determine role (for Cognito cleanup)
    members = permissions_repo.list_team_members(team_id)
    target_member = None
    for m in members:
        if m.get('user_sub') == user_sub:
            target_member = m
            break

    if not target_member:
        return create_response(404, {'error': 'Membership not found'})

    member_role = target_member.get('role', '')

    # Remove membership from DynamoDB
    permissions_repo.remove_membership(user_sub, team_id)

    # Remove from Cognito group
    user_pool_id = os.environ.get('USER_POOL_ID', '')
    if user_pool_id and member_role:
        try:
            cognito_sync.remove_user_from_team_role(user_sub, team_id, member_role, user_pool_id)
        except Exception as e:
            # Membership already removed from DynamoDB — log but don't fail
            logger.error(f"Failed to remove member from Cognito group for team {team_id}: {e}")

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='member_remove',
        target={'user_sub': user_sub, 'team_id': team_id},
        details={'role': member_role},
    )

    logger.info(f"Removed member from team {team_id}")
    return {
        'statusCode': 204,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
        'body': '',
    }
