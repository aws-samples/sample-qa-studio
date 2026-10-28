import lambda_init  # noqa: F401 — must be first import
import json
import os
import logging
from typing import Any, Dict
from utils import create_response, require_scopes
import permissions_repo
import cognito_sync

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new team.

    Requires api/admin scope.
    Creates the team in DynamoDB and ensures Cognito groups exist.

    Request body:
        { "name": "Team Name" }

    Returns:
        201: Created team record
        400: Invalid input or duplicate name
        403: Insufficient permissions
    """
    user_identity, error_response = require_scopes(event, ['api/admin'])
    if error_response:
        return error_response

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    name = body.get('name', '').strip()
    if not name:
        return create_response(400, {'error': 'name is required'})

    if len(name) > 100:
        return create_response(400, {'error': 'name must be 100 characters or less'})

    # Check for duplicate team name
    if permissions_repo.team_name_exists(name):
        return create_response(400, {'error': f'Team with name "{name}" already exists'})

    # Create team record in DynamoDB
    created_by = user_identity.get('sub', user_identity.get('identity', ''))
    team = permissions_repo.create_team(name, created_by)

    # Create Cognito groups for the team
    user_pool_id = os.environ.get('USER_POOL_ID', '')
    if user_pool_id:
        try:
            cognito_sync.ensure_team_groups(team['id'], user_pool_id)
        except Exception as e:
            logger.error(f"Failed to create Cognito groups for team {team['id']}: {e}. Compensating DynamoDB write.")
            try:
                permissions_repo.delete_team(team['id'])
            except Exception as comp_err:
                logger.error(f"Compensation failed for team {team['id']}: {comp_err}")
            return create_response(500, {'error': 'Failed to create team groups. Please retry.'})

    # Clean response — remove DynamoDB internal keys
    response_body = {
        'id': team['id'],
        'name': team['name'],
        'created_by': team['created_by'],
        'created_at': team['created_at'],
    }

    logger.info(f"Created team: {team['id']} ({name})")
    return create_response(201, response_body)
