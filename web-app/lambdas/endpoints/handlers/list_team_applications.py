import lambda_init  # noqa: F401 — must be first import
import logging
from typing import Any, Dict
from utils import create_response, require_scopes, validate_path_id
from resource_auth import require_team_role
import permissions_repo

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_INTERNAL_KEYS = ('pk', 'sk', 'gsi2pk', 'gsi2sk')


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """List applications owned by a team. Members of the team or admins only."""
    user_identity, error_response = require_scopes(event, ['api/applications.read'])
    if error_response:
        return error_response

    team_id, error = validate_path_id(
        (event.get('pathParameters') or {}).get('id'), 'team ID'
    )
    if error:
        return error

    role_err = require_team_role(user_identity, team_id, 'viewer', 'Team membership required')
    if role_err:
        return role_err

    team_apps = permissions_repo.list_team_apps(team_id)
    for app in team_apps:
        for key in _INTERNAL_KEYS:
            app.pop(key, None)

    return create_response(200, team_apps)
