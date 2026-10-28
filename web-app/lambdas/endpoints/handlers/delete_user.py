import lambda_init  # noqa: F401 — must be first import
import os
import logging
from typing import Any, Dict
import boto3
from utils import create_response, require_scopes, aws_error_code
import permissions_repo
import cognito_sync
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a user from Cognito and remove all team memberships.

    Requires api/admin scope.

    Path parameters:
        userId: Cognito user sub

    Returns:
        204: User deleted
        400: Missing userId
        403: Insufficient permissions
        409: Cannot delete the last admin
        500: Cognito failure
    """
    user_identity, error_response = require_scopes(event, ['api/admin'])
    if error_response:
        return error_response

    path_params = event.get('pathParameters') or {}
    user_sub = path_params.get('userId', '').strip()
    if not user_sub:
        return create_response(400, {'error': 'userId path parameter is required'})

    user_pool_id = os.environ.get('USER_POOL_ID', '')
    if not user_pool_id:
        return create_response(500, {'error': 'USER_POOL_ID not configured'})

    # Last-admin guard (global 'admins' group). Fail closed if the check fails.
    try:
        if cognito_sync.is_last_studio_admin(user_sub, user_pool_id):
            return create_response(409, {'error': 'Cannot delete the last admin'})
    except Exception as e:
        logger.error(f"Last-admin check failed: {aws_error_code(e)}")
        return create_response(500, {'error': 'Failed to verify admin membership'})

    user_teams = permissions_repo.list_user_teams(user_sub)

    # Remove all team memberships from DynamoDB
    for m in user_teams:
        team_id = m.get('team_id', '')
        try:
            permissions_repo.remove_membership(user_sub, team_id)
        except Exception as e:
            logger.warning(f"Failed to remove membership from team {team_id}: {e}")

    # Delete user from Cognito
    client = boto3.client('cognito-idp')
    try:
        client.admin_delete_user(
            UserPoolId=user_pool_id,
            Username=user_sub,
        )
    except client.exceptions.UserNotFoundException:
        logger.info(f"User not found in Cognito (already deleted)")
    except Exception as e:
        logger.error(f"Failed to delete user from Cognito: {e}")
        return create_response(500, {'error': 'Failed to delete user from Cognito'})

    # Audit log
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    log_permission_change(
        actor=actor,
        action='user_delete',
        target={'user_sub': user_sub},
        details={'removed_teams': [m.get('team_id', '') for m in user_teams]},
    )

    logger.info(f"Deleted user")
    return {
        'statusCode': 204,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
        'body': '',
    }
