import lambda_init  # noqa: F401 — must be first import
import json
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, require_scopes
import permissions_repo
from role_scopes import TEAM_ROLES
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 'admin' means the studio-wide 'admins' group; anything else is a team role.
_VALID_ROLES = ('admin',) + TEAM_ROLES


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new user in Cognito with optional team assignment.

    Requires api/admin scope.

    Request body:
        { "email": "user@example.com", "teamId"?: "...", "role"?: "editor" }

    Returns:
        201: Created user {userId, email, teams}
        400: Invalid input
        403: Insufficient permissions
        500: Cognito failure
    """
    user_identity, error_response = require_scopes(event, ['api/admin'])
    if error_response:
        return error_response

    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    email = body.get('email', '').strip()
    team_id = body.get('teamId', '').strip()
    role = body.get('role', '').strip()

    # Backward compat: old UI sends {email, groups: ['users'|'admins']}
    groups = body.get('groups', [])
    if groups and not team_id:
        if not email:
            return create_response(400, {'error': 'email is required'})
        if not isinstance(groups, list) or not groups:
            return create_response(400, {'error': 'At least one group must be specified'})
        valid_groups = ['users', 'admins']
        invalid = [g for g in groups if g not in valid_groups]
        if invalid:
            return create_response(400, {'error': f'Invalid groups: {", ".join(invalid)}. Valid: {", ".join(valid_groups)}'})
        # Map legacy groups to the new team model: skip team assignment,
        # just create user and add to Cognito groups directly
        user_pool_id = os.environ.get('USER_POOL_ID', '')
        client = boto3.client('cognito-idp')
        try:
            response = client.admin_create_user(
                UserPoolId=user_pool_id,
                Username=email,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'true'},
                ],
                DesiredDeliveryMediums=['EMAIL'],
            )
        except client.exceptions.UsernameExistsException:
            return create_response(400, {'error': 'User with this email already exists'})
        except Exception as e:
            logger.error(f"Failed to create Cognito user: {e}")
            return create_response(500, {'error': 'Failed to create user'})
        cognito_user = response.get('User', {})
        user_sub = cognito_user.get('Username', '')
        for group in groups:
            try:
                client.admin_add_user_to_group(
                    UserPoolId=user_pool_id, Username=user_sub, GroupName=group)
            except Exception as e:
                logger.warning(f"Failed to add to group {group}: {e}")
        return create_response(201, {'username': user_sub, 'email': email, 'groups': groups})

    if not email:
        return create_response(400, {'error': 'email is required'})

    # If team assignment is requested, validate role
    if team_id and not role:
        role = 'viewer'  # Default role when team is specified
    if role and role not in _VALID_ROLES:
        return create_response(400, {'error': f'Invalid role. Must be one of: {", ".join(_VALID_ROLES)}'})

    # If team specified, verify it exists
    if team_id:
        team = permissions_repo.get_team(team_id)
        if not team:
            return create_response(404, {'error': 'Team not found'})

    user_pool_id = os.environ.get('USER_POOL_ID', '')
    if not user_pool_id:
        return create_response(500, {'error': 'USER_POOL_ID not configured'})

    # Create user in Cognito
    client = boto3.client('cognito-idp')
    try:
        response = client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'},
            ],
            DesiredDeliveryMediums=['EMAIL'],
        )
    except client.exceptions.UsernameExistsException:
        return create_response(400, {'error': 'User with this email already exists'})
    except Exception as e:
        logger.error(f"Failed to create Cognito user: {e}")
        return create_response(500, {'error': 'Failed to create user'})

    # Extract the sub from the created user
    cognito_user = response.get('User', {})
    user_sub = cognito_user.get('Username', '')
    attrs = {a['Name']: a['Value'] for a in cognito_user.get('Attributes', [])}
    actual_sub = attrs.get('sub', user_sub)

    # Admin is a studio-wide role — teamless. Add to the global 'admins' group
    # and ignore any team selection.
    teams = []
    if role == 'admin':
        try:
            client.admin_add_user_to_group(
                UserPoolId=user_pool_id,
                Username=actual_sub,
                GroupName='admins',
            )
        except Exception as e:
            logger.warning(f"Failed to add user {actual_sub} to 'admins' group: {e}")
    elif team_id and role:
        try:
            permissions_repo.add_membership(team_id, actual_sub, role)

            # Sync to Cognito group
            group_name = f'team-{team_id}-{role}'
            try:
                client.admin_add_user_to_group(
                    UserPoolId=user_pool_id,
                    Username=actual_sub,
                    GroupName=group_name,
                )
            except Exception as e:
                logger.warning(f"Failed to add user to Cognito group {group_name}: {e}")

            team = permissions_repo.get_team(team_id)
            teams.append({
                'teamId': team_id,
                'name': team.get('name', '') if team else '',
                'role': role,
            })
        except Exception as e:
            logger.error(f"Failed to assign user {actual_sub} to team {team_id}: {e}")

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='user_create',
        target={'user_sub': actual_sub, 'email': email},
        details={'team_id': team_id, 'role': role},
    )

    response_body = {
        'userId': actual_sub,
        'email': email,
        'teams': teams,
    }

    logger.info(f"Created user sub={actual_sub}")
    return create_response(201, response_body)
