import lambda_init  # noqa: F401 — must be first import
import logging
from typing import Any, Dict
from utils import create_response, extract_user_identity, validate_path_id
import permissions_repo
from resource_auth import require_team_role
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Revoke a shared access grant.

    The path {id} refers to the OWNING team. The {grantId} identifies the grant.
    Caller must be admin or team-lead of the owning team.

    Path parameters:
        id: Owner team ID
        grantId: Grant ID to revoke

    Returns:
        204: Grant revoked
        403: Insufficient permissions
        404: Grant not found
    """
    # Auth: admin or team-lead of the owning team
    user_identity = extract_user_identity(event)
    team_id_raw = (event.get('pathParameters') or {}).get('id', '')
    auth_error = require_team_role(user_identity, team_id_raw, 'team_lead',
                                   'Admin or team lead of the owning team required')
    if auth_error:
        return auth_error

    owner_team_id, error = validate_path_id(
        (event.get('pathParameters') or {}).get('id'), 'team ID'
    )
    if error:
        return error

    path_params = event.get('pathParameters') or {}
    grant_id = path_params.get('grantId', '').strip()
    if not grant_id:
        return create_response(400, {'error': 'grantId path parameter is required'})

    # Find the grant by listing shares for this team and matching grant_id
    grants = permissions_repo.list_shared_access(owner_team_id)
    target_grant = None
    for g in grants:
        if g.get('grant_id') == grant_id:
            target_grant = g
            break

    if not target_grant:
        return create_response(404, {'error': 'Grant not found'})

    # Revoke the grant
    permissions_repo.revoke_shared_access(
        owner_team_id=owner_team_id,
        target_team_id=target_grant.get('target_team_id', ''),
        app_id=target_grant.get('app_id', ''),
    )

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='revoke_access',
        target={
            'owner_team_id': owner_team_id,
            'target_team_id': target_grant.get('target_team_id', ''),
            'app_id': target_grant.get('app_id', ''),
        },
        details={'grant_id': grant_id},
    )

    logger.info(f"Revoked grant {grant_id} from team {owner_team_id}")
    return {
        'statusCode': 204,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
        'body': '',
    }
