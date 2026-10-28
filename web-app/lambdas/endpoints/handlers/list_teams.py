import lambda_init  # noqa: F401 — must be first import
import logging
from typing import Any, Dict
from utils import create_response, require_scopes, extract_user_identity
import permissions_repo
from resource_auth import has_team_role

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    List teams.

    Admins get the full list enriched with member/app counts. Team leads get
    a minimal list ({id, name} only) — enough to populate the shared-access
    grant target dropdown without exposing other teams' membership details.

    Returns:
        200: List of team summaries
        403: Insufficient permissions (not admin or team lead)
    """
    user_identity, error_response = require_scopes(event, ['api/admin'])

    if error_response:
        # Not admin — allow team leads a minimal list for the grant dropdown
        identity = extract_user_identity(event)
        if not has_team_role(identity, None, 'team_lead'):
            return error_response

        teams = permissions_repo.list_teams()
        minimal = [{'id': t.get('id', ''), 'name': t.get('name', '')} for t in teams]
        logger.info(f"Listed {len(minimal)} teams (minimal, team-lead)")
        return create_response(200, minimal)

    teams = permissions_repo.list_teams()

    # Enrich with member and app counts (admin only)
    results = []
    for team in teams:
        team_id = team.get('id', '')
        members = permissions_repo.list_team_members(team_id)
        apps = permissions_repo.list_team_apps(team_id)

        results.append({
            'id': team_id,
            'name': team.get('name', ''),
            'memberCount': len(members),
            'applicationCount': len(apps),
        })

    logger.info(f"Listed {len(results)} teams")
    return create_response(200, results)
