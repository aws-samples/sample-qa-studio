import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import get_table_name, extract_user_identity, no_content_response
from resource_auth import require_resource_access, app_from_path, require_owner_team_lead
from perm_audit import log_permission_change
import permissions_repo

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('delete', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete an application. Team Lead of the owning team or studio admin only.

    Revokes the app's share grants, clears application_id on its use cases
    (which makes them admin-only), and returns 204.
    """
    user_identity = extract_user_identity(event)
    app_id = event['pathParameters']['id']  # validated by app_from_path

    owner_team_id = permissions_repo.get_app_owner(app_id)
    role_err = require_owner_team_lead(user_identity, owner_team_id)
    if role_err:
        return role_err
    if owner_team_id:
        _revoke_app_grants(user_identity, owner_team_id, app_id)

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    # Query all association records under this application
    assoc_response = table.query(
        KeyConditionExpression=Key('pk').eq(f'APPLICATION#{app_id}') & Key('sk').begins_with('USECASE#')
    )

    # Clear application_id from associated usecases and delete association records
    with table.batch_writer() as batch:
        for item in assoc_response.get('Items', []):
            usecase_id = item['sk'].replace('USECASE#', '')
            # Remove association record
            batch.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': item['sk']})
            # Clear application_id on the usecase
            try:
                table.update_item(
                    Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'},
                    UpdateExpression='REMOVE application_id',
                    ConditionExpression='attribute_exists(pk)',
                )
            except Exception:
                logger.warning(f"Could not clear application_id from usecase {usecase_id}")

    # Delete METADATA record
    table.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'})

    # Delete index record
    table.delete_item(Key={'pk': 'APPLICATIONS', 'sk': f'APPLICATION#{app_id}'})

    logger.info(f"Deleted application {app_id}")
    return no_content_response()


def _revoke_app_grants(user_identity: dict, owner_team_id: str, app_id: str) -> None:
    """Revoke every share grant the owner team issued for this app."""
    actor = {'sub': user_identity.get('sub', ''), 'email': user_identity.get('email', '')}
    for grant in permissions_repo.list_shared_access(owner_team_id):
        if grant.get('app_id') != app_id:
            continue
        target_team_id = grant.get('target_team_id', '')
        permissions_repo.revoke_shared_access(owner_team_id, target_team_id, app_id)
        log_permission_change(
            actor=actor,
            action='revoke_access',
            target={'owner_team_id': owner_team_id, 'target_team_id': target_team_id, 'app_id': app_id},
            details={'grant_id': grant.get('grant_id', ''), 'reason': 'app_deleted'},
        )
