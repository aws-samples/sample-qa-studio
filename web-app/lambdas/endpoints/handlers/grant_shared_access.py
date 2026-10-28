import lambda_init  # noqa: F401 — must be first import
import json
import logging
from typing import Any, Dict
from utils import create_response, extract_user_identity, validate_path_id
import permissions_repo
from resource_auth import require_team_role
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_VALID_LEVELS = {'view', 'execute', 'full'}


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Grant shared access to an application for a target team.

    The path {id} refers to the OWNING team — the caller must be admin or team-lead
    of the owning team.

    Path parameters:
        id: Owner team ID

    Request body:
        { "targetTeamId": "...", "appId": "...", "level": "view|execute|full" }

    Returns:
        201: Grant record {grantId, ownerTeamId, targetTeamId, appId, level, grantedAt}
        400: Invalid input or owner==target
        403: Insufficient permissions
        404: Team not found
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

    # Verify owning team exists
    team = permissions_repo.get_team(owner_team_id)
    if not team:
        return create_response(404, {'error': 'Team not found'})

    # Parse body
    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    target_team_id = body.get('targetTeamId', '').strip()
    app_id = body.get('appId', '').strip()
    level = body.get('level', '').strip()

    if not target_team_id:
        return create_response(400, {'error': 'targetTeamId is required'})
    if not app_id:
        return create_response(400, {'error': 'appId is required'})
    if not level:
        return create_response(400, {'error': 'level is required'})
    if level not in _VALID_LEVELS:
        return create_response(400, {'error': f'Invalid level. Must be one of: {", ".join(sorted(_VALID_LEVELS))}'})

    # Verify target team exists
    target_team = permissions_repo.get_team(target_team_id)
    if not target_team:
        return create_response(404, {'error': 'Target team not found'})

    # Verify the app is actually owned by this team
    app_owner = permissions_repo.get_app_owner(app_id)
    if app_owner != owner_team_id:
        return create_response(400, {'error': 'Application is not owned by this team'})

    # Grant shared access (repo handles owner==target check)
    try:
        grant = permissions_repo.grant_shared_access(
            owner_team_id=owner_team_id,
            target_team_id=target_team_id,
            app_id=app_id,
            level=level,
            actor=user_identity.get('sub', ''),
        )
    except ValueError as e:
        return create_response(400, {'error': str(e)})

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='grant_access',
        target={'owner_team_id': owner_team_id, 'target_team_id': target_team_id, 'app_id': app_id},
        details={'level': level, 'grant_id': grant.get('grant_id', '')},
    )

    response_body = {
        'grantId': grant.get('grant_id', ''),
        'ownerTeamId': owner_team_id,
        'targetTeamId': target_team_id,
        'targetTeamName': target_team.get('name', ''),
        'appId': app_id,
        'level': level,
        'grantedAt': grant.get('granted_at', ''),
    }

    logger.info(f"Granted {level} access on app {app_id} to team {target_team_id}")
    return create_response(201, response_body)
