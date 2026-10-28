import lambda_init  # noqa: F401 — must be first import
import json
import logging
from typing import Any, Dict
from utils import create_response, require_scopes, validate_path_id
import permissions_repo
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reassign an application to a different team.

    Requires api/admin scope.

    Path parameters:
        id: Application ID

    Request body:
        { "targetTeamId": "..." }

    Returns:
        200: {appId, targetTeamId, previousTeamId}
        400: Invalid input
        403: Insufficient permissions
        404: Team not found
    """
    user_identity, error_response = require_scopes(event, ['api/admin'])
    if error_response:
        return error_response

    app_id, error = validate_path_id(
        (event.get('pathParameters') or {}).get('id'), 'application ID'
    )
    if error:
        return error

    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    target_team_id = body.get('targetTeamId', '').strip()
    if not target_team_id:
        return create_response(400, {'error': 'targetTeamId is required'})

    # Verify target team exists
    team = permissions_repo.get_team(target_team_id)
    if not team:
        return create_response(404, {'error': 'Target team not found'})

    # Get current owner
    previous_owner = permissions_repo.get_app_owner(app_id)

    # Reassign the app itself...
    permissions_repo.set_app_owner(app_id, target_team_id)

    # ...then cascade ownership to the app's use cases and test suites so the
    # new team can actually see them. Without this, resources added while the
    # app was unowned/owned-by-another-team stay invisible to the new team —
    # the failure mode when migrating orphan use cases into a team.
    cascade = permissions_repo.set_app_resources_owner(app_id, target_team_id)

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='app_reassign',
        target={'app_id': app_id},
        details={
            'previous_team_id': previous_owner or '',
            'new_team_id': target_team_id,
            'reassigned_usecases': cascade.get('usecases', 0),
            'reassigned_suites': cascade.get('suites', 0),
        },
    )

    logger.info(
        f"Reassigned application {app_id} from {previous_owner} to {target_team_id} "
        f"(cascaded {cascade})"
    )
    return create_response(200, {
        'appId': app_id,
        'targetTeamId': target_team_id,
        'previousTeamId': previous_owner or '',
        'reassignedUsecases': cascade.get('usecases', 0),
        'reassignedSuites': cascade.get('suites', 0),
    })
