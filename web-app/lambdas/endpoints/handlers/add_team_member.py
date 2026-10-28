import lambda_init  # noqa: F401 — must be first import
import json
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, extract_user_identity, validate_path_id
import permissions_repo
from resource_auth import require_team_role, validate_team_role
import cognito_sync
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a member to a team.

    Requires api/admin scope OR caller must be team lead of the target team.
    Implements the membership mutation saga:
      1. permissions_repo.add_membership (DynamoDB)
      2. cognito_sync.set_user_role (Cognito — adds to group)
      On step-2 failure: compensate step-1 (remove membership), return 500.

    Path parameters:
        id: Team ID

    Request body:
        { "userId": "cognito-sub", "role": "editor" }

    Returns:
        201: Created membership {team_id, user_sub, role, added_at}
        400: Invalid input
        403: Insufficient permissions
        404: Team not found
        500: Saga failure (compensated)
    """
    # Auth: admin or team-lead of this team
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

    # Parse body
    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    user_input = body.get('userId', '').strip()
    role = body.get('role', '').strip()

    if not user_input:
        return create_response(400, {'error': 'userId is required'})
    if not role:
        return create_response(400, {'error': 'role is required'})
    role_error = validate_team_role(role)
    if role_error:
        return role_error

    # Resolve email to Cognito sub and username
    user_sub = user_input
    cognito_username = user_input
    if '@' in user_input:
        user_pool_id_check = os.environ.get('USER_POOL_ID', '')
        if user_pool_id_check:
            cognito_client = boto3.client('cognito-idp')
            try:
                resp = cognito_client.admin_get_user(UserPoolId=user_pool_id_check, Username=user_input)
                attrs = {a['Name']: a['Value'] for a in resp.get('UserAttributes', [])}
                user_sub = attrs.get('sub', resp.get('Username', user_input))
                cognito_username = resp.get('Username', user_input)
            except cognito_client.exceptions.UserNotFoundException:
                return create_response(404, {'error': f'User {user_input} not found in Cognito'})
            except Exception as e:
                logger.warning(f"Failed to resolve user {user_input}: {e}")
    else:
        cognito_username = user_input

    # Check if user is already a member
    existing_members = permissions_repo.list_team_members(team_id)
    for member in existing_members:
        if member.get('user_sub') == user_sub:
            return create_response(400, {'error': 'User is already a member of this team'})

    # SAGA Step 1: Write membership to DynamoDB (system of record)
    membership = permissions_repo.add_membership(team_id, user_sub, role)

    # SAGA Step 2: Sync to Cognito (projection)
    user_pool_id = os.environ.get('USER_POOL_ID', '')
    if user_pool_id:
        try:
            _add_user_to_team_group(cognito_username, team_id, role, user_pool_id)
        except Exception as e:
            # Compensate: remove the DynamoDB membership
            logger.error(f"Cognito sync failed for team {team_id}: {e}. Compensating.")
            try:
                permissions_repo.remove_membership(user_sub, team_id)
            except Exception as comp_err:
                logger.error(f"Compensation failed: {comp_err}")
            return create_response(500, {'error': 'Failed to sync team membership. Please retry.'})

    # SAGA Step 3: Audit log (best-effort, never fails the request)
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='member_add',
        target={'user_sub': user_sub, 'team_id': team_id},
        details={'role': role},
    )

    response_body = {
        'team_id': team_id,
        'user_sub': user_sub,
        'role': role,
        'added_at': membership.get('added_at', ''),
    }

    logger.info(f"Added member to team {team_id} as {role}")
    return create_response(201, response_body)


def _add_user_to_team_group(cognito_username: str, team_id: str, role: str, user_pool_id: str) -> None:
    """Add a user to the appropriate team role Cognito group."""
    client = boto3.client('cognito-idp')
    group_name = f'team-{team_id}-{role}'

    client.admin_add_user_to_group(
        UserPoolId=user_pool_id,
        Username=cognito_username,
        GroupName=group_name,
    )
    logger.info(f"Added user to Cognito group {group_name}")
