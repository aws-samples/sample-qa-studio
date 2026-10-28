import lambda_init  # noqa: F401 — must be first import
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, require_scopes
import permissions_repo
from role_scopes import is_admin_group

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all users with their team memberships.

    Requires api/admin scope.

    Returns:
        200: List of users [{userId, email, teams: [{teamId, name, role}]}]
        403: Insufficient permissions
    """
    user_identity, error_response = require_scopes(event, ['api/admin'])
    if error_response:
        return error_response

    user_pool_id = os.environ.get('USER_POOL_ID', '')
    if not user_pool_id:
        return create_response(500, {'error': 'USER_POOL_ID not configured'})

    # List users from Cognito
    client = boto3.client('cognito-idp')
    users = []
    pagination_token = None

    while True:
        kwargs = {
            'UserPoolId': user_pool_id,
            'Limit': 60,
        }
        if pagination_token:
            kwargs['PaginationToken'] = pagination_token

        response = client.list_users(**kwargs)

        for cognito_user in response.get('Users', []):
            user_sub = cognito_user.get('Username', '')
            attrs = {a['Name']: a['Value'] for a in cognito_user.get('Attributes', [])}
            email = attrs.get('email', '')

            # Determine studio-wide admin status from Cognito group membership
            is_admin = False
            try:
                groups_resp = client.admin_list_groups_for_user(
                    UserPoolId=user_pool_id, Username=user_sub)
                group_names = [g.get('GroupName', '') for g in groups_resp.get('Groups', [])]
                is_admin = any(is_admin_group(g) for g in group_names)
            except Exception as e:
                logger.warning(f"Failed to list groups: {e}")

            # Get team memberships from DynamoDB
            memberships = permissions_repo.list_user_teams(user_sub)
            teams = []
            for m in memberships:
                team_id = m.get('team_id', '')
                team = permissions_repo.get_team(team_id)
                team_name = team.get('name', '') if team else ''
                teams.append({
                    'teamId': team_id,
                    'name': team_name,
                    'role': m.get('role', ''),
                })

            users.append({
                'userId': user_sub,
                'email': email,
                'teams': teams,
                'isAdmin': is_admin,
            })

        pagination_token = response.get('PaginationToken')
        if not pagination_token:
            break

    logger.info(f"Listed {len(users)} users")
    return create_response(200, users)
