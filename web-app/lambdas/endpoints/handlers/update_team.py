import lambda_init  # noqa: F401 — must be first import
import json
import logging
from typing import Any, Dict
from utils import create_response, require_scopes, validate_path_id
import permissions_repo

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a team's metadata (name, description).

    Requires api/admin scope.

    Path parameters:
        id: Team ID

    Request body:
        { "name"?: "New Name", "description"?: "New desc" }

    Returns:
        200: Updated team record
        400: Invalid input or duplicate name
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

    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    # Collect updatable fields
    fields = {}

    name = body.get('name')
    if name is not None:
        name = name.strip()
        if not name:
            return create_response(400, {'error': 'name cannot be empty'})
        if len(name) > 100:
            return create_response(400, {'error': 'name must be 100 characters or less'})
        # Check for duplicate name (exclude current team)
        if permissions_repo.team_name_exists(name):
            existing_team = permissions_repo.get_team(team_id)
            if not existing_team or existing_team.get('name', '').lower() != name.lower():
                return create_response(400, {'error': f'Team with name "{name}" already exists'})
        fields['name'] = name

    description = body.get('description')
    if description is not None:
        description = description.strip()
        if len(description) > 500:
            return create_response(400, {'error': 'description must be 500 characters or less'})
        fields['description'] = description

    if not fields:
        return create_response(400, {'error': 'At least one field (name, description) must be provided'})

    updated = permissions_repo.update_team(team_id, fields)
    if updated is None:
        return create_response(404, {'error': 'Team not found'})

    response_body = {
        'id': updated.get('id', ''),
        'name': updated.get('name', ''),
        'description': updated.get('description', ''),
        'created_by': updated.get('created_by', ''),
        'created_at': updated.get('created_at', ''),
    }

    logger.info(f"Updated team {team_id}: {list(fields.keys())}")
    return create_response(200, response_body)
