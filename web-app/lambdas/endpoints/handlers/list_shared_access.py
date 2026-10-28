import lambda_init  # noqa: F401 — must be first import
import logging
from typing import Any, Dict
from utils import create_response, extract_user_identity, validate_path_id
import permissions_repo
from resource_auth import require_team_role

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all shared access grants issued BY a team (outgoing shares).

    Requires api/admin scope OR caller must be team lead of the team.

    Path parameters:
        id: Team ID (the owner/grantor)

    Returns:
        200: List of grants [{grantId, targetTeamId, targetTeamName, appId, accessLevel, grantedAt}]
        403: Insufficient permissions
        404: Team not found
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

    # Verify team exists
    team = permissions_repo.get_team(team_id)
    if not team:
        return create_response(404, {'error': 'Team not found'})

    grants = permissions_repo.list_shared_access(team_id)

    # Enrich with target team names
    results = []
    for g in grants:
        target_team_id = g.get('target_team_id', '')
        target_team = permissions_repo.get_team(target_team_id)
        target_team_name = target_team.get('name', '') if target_team else target_team_id

        results.append({
            'grantId': g.get('grant_id', ''),
            'targetTeamId': target_team_id,
            'targetTeamName': target_team_name,
            'appId': g.get('app_id', ''),
            'accessLevel': g.get('level', ''),
            'grantedAt': g.get('granted_at', ''),
        })

    logger.info(f"Listed {len(results)} shared access grants for team {team_id}")
    return create_response(200, results)
