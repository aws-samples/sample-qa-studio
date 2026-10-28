import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import get_table_name, create_response, require_scopes
from resource_auth import can_view_testcase_batch

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to list use cases from Amazon DynamoDB.

    Team-scoped: admins see all use cases; team members see only use cases
    owned by their team(s) plus those in apps shared with their team(s).

    Args:
        event: API Gateway proxy request event
        context: Lambda context

    Returns:
        API Gateway proxy response with list of use cases
    """

    try:
        # Validate scope (requires usecases.read or admin)
        identity, error_response = require_scopes(event, ['api/usecases.read'])
        if error_response:
            return error_response

        # Initialize Amazon DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        # Query Amazon DynamoDB for all use cases
        response = table.query(
            KeyConditionExpression=Key('pk').eq('USECASES') & Key('sk').begins_with('USECASE#')
        )

        usecases = response.get('Items', [])

        # Team-scoping: admins see everything; otherwise filter to the caller's
        # teams (owned) plus apps shared with their teams.
        if not identity.get('is_admin', False):
            team_ids = {tr.get('team_id') for tr in identity.get('team_roles', []) if tr.get('team_id')}

            # App IDs shared with the caller's teams (so shared use cases remain visible)
            import permissions_repo
            shared_app_ids = set()
            for tid in team_ids:
                try:
                    for grant in permissions_repo.list_apps_shared_with_team(tid):
                        app_id = grant.get('app_id') or grant.get('application_id')
                        if app_id:
                            shared_app_ids.add(app_id)
                except Exception as e:
                    logger.warning(f"shared-access lookup failed for team {tid}: {e}")

            def visible(uc):
                if not uc.get('application_id'):
                    return False  # orphaned use cases are admin-only
                owner = uc.get('owner_team_id')
                if owner and owner in team_ids:
                    return True
                if uc.get('application_id') in shared_app_ids:
                    return True
                return False

            usecases = [uc for uc in usecases if visible(uc)]

            # Per-test-case visibility overrides narrow the list (BR-3);
            # admins bypass them. One BatchGetItem per 100 use cases.
            shown = can_view_testcase_batch(
                identity, {uc['id']: uc.get('owner_team_id') for uc in usecases if uc.get('id')})
            usecases = [uc for uc in usecases if uc.get('id') in shown]

        # Return successful response
        return create_response(200, {'usecases': usecases})

    except Exception as e:
        logger.error(f"Error listing use cases: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
