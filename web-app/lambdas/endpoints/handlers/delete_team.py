import lambda_init  # noqa: F401 — must be first import
import json
import os
import logging
from typing import Any, Dict
from utils import create_response, no_content_response, require_scopes, validate_path_id
import permissions_repo
import cognito_sync
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a team and all associated data.

    Requires api/admin scope.
    If the team has more than 5 members, the body must include {"confirm": true}.

    Path parameters:
        id: Team ID

    Request body (optional):
        { "confirm": true }

    Returns:
        204: Team deleted (counts are recorded in the team_delete audit entry)
        400: Bulk confirm required (>5 members without confirm flag)
        403: Insufficient permissions
        404: Team not found
    """
    user_identity, error_response = require_scopes(event, ['api/admin'])
    if error_response:
        return error_response

    team_id, error = validate_path_id(
        (event.get('pathParameters') or {}).get('id'), 'team ID'
    )
    if error:
        return error

    # Verify team exists
    team = permissions_repo.get_team(team_id)
    if not team:
        return create_response(404, {'error': 'Team not found'})

    # Check member count for bulk confirm requirement
    members = permissions_repo.list_team_members(team_id)
    if len(members) > 5:
        try:
            body = json.loads(event.get('body') or '{}')
        except json.JSONDecodeError:
            body = {}

        if not body.get('confirm', False):
            return create_response(400, {
                'error': f'Team has {len(members)} members. Include {{"confirm": true}} to proceed.',
                'memberCount': len(members),
            })

    # Delete team from DynamoDB (handles memberships, orphans apps)
    result = permissions_repo.delete_team(team_id)

    # Delete Cognito groups for this team
    user_pool_id = os.environ.get('USER_POOL_ID', '')
    if user_pool_id:
        try:
            cognito_sync.delete_team_groups(team_id, user_pool_id)
        except Exception as e:
            # Team is already deleted from DynamoDB — log but don't fail
            logger.error(f"Failed to delete Cognito groups for team {team_id}: {e}")

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='team_delete',
        target={'team_id': team_id, 'team_name': team.get('name', '')},
        details={
            'deleted_members_count': result.get('deleted_members_count', 0),
            'orphaned_apps_count': result.get('orphaned_apps_count', 0),
        },
    )

    logger.info(f"Deleted team {team_id} ({team.get('name', '')})")
    # Counts stay in the team_delete audit entry above.
    return no_content_response()
