import lambda_init  # noqa: F401 — must be first import
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, extract_user_identity, validate_path_id
import permissions_repo
from resource_auth import require_team_role

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all members of a team.

    Requires api/admin scope OR caller must be team lead of the target team.

    Path parameters:
        id: Team ID

    Returns:
        200: List of members [{userId, role, addedAt}]
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

    members = permissions_repo.list_team_members(team_id)

    # Resolve user subs to emails via Cognito
    user_pool_id = os.environ.get('USER_POOL_ID', '')
    results = []
    for m in members:
        user_sub = m.get('user_sub', '')
        email = user_sub
        if user_pool_id and user_sub:
            try:
                client = boto3.client('cognito-idp')
                resp = client.admin_get_user(UserPoolId=user_pool_id, Username=user_sub)
                attrs = {a['Name']: a['Value'] for a in resp.get('UserAttributes', [])}
                email = attrs.get('email', user_sub)
            except Exception:
                pass
        results.append({
            'userId': user_sub,
            'email': email,
            'role': m.get('role', ''),
            'joinedAt': m.get('added_at', ''),
        })

    logger.info(f"Listed {len(results)} members for team {team_id}")
    return create_response(200, results)
