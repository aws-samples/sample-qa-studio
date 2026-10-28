import json
import logging
from typing import Any, Dict, Optional
import boto3
from utils import create_response, get_table_name, validate_path_id, get_current_timestamp
from resource_auth import require_resource_access, app_from_path, authorize_resource, owner_of
import permissions_repo

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add or remove use cases on an application.

    Requires edit on the target app (decorator) and edit on each use case's
    current app, so nobody can pull in or detach another team's use cases.
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    usecase_ids = body.get('usecase_ids', [])
    action = body.get('action', 'add')

    if not usecase_ids or not isinstance(usecase_ids, list):
        return create_response(400, {'error': 'usecase_ids must be a non-empty list'})

    usecase_err = _authorize_current_apps(event, app_id, usecase_ids)
    if usecase_err:
        return usecase_err

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    if action == 'remove':
        return _remove_usecases(table, app_id, usecase_ids)

    return _add_usecases(
        table, app_id, usecase_ids, body.get('environment', ''),
        permissions_repo.get_app_owner(app_id),
    )


def _authorize_current_apps(event: Dict[str, Any], app_id: str,
                            usecase_ids: list) -> Optional[Dict[str, Any]]:
    """
    Require edit on the app each use case currently belongs to. Use cases
    already in `app_id` are covered by the decorator; orphaned use cases
    (no app) are admin-only.

    Returns:
        None when allowed, otherwise a 400/403/404 response.
    """
    for usecase_id in usecase_ids:
        _, err = validate_path_id(usecase_id if isinstance(usecase_id, str) else None, 'usecase ID')
        if err:
            return err
        owner = permissions_repo.get_usecase_owner(usecase_id)
        if owner is None:
            return create_response(404, {'error': f'Use case {usecase_id} not found'})
        current_app_id, current_owner = owner_of(owner)
        if current_app_id == app_id:
            continue
        _, auth_err = authorize_resource(event, current_app_id or '', 'edit',
                                         owner_team_id=current_owner)
        if auth_err:
            return auth_err
    return None


def _add_usecases(table, app_id: str, usecase_ids: list, environment: str,
                  owner_team_id: Optional[str]) -> Dict[str, Any]:
    now = get_current_timestamp()

    # 1. Write the association records (per-app environment lives here).
    with table.batch_writer() as batch:
        for usecase_id in usecase_ids:
            batch.put_item(Item={
                'pk': f'APPLICATION#{app_id}',
                'sk': f'USECASE#{usecase_id}',
                'associated_at': now,
                'environment': environment,
            })

    # 2. Stamp application_id (and the inherited owner_team_id) onto each use
    #    case item. The app-detail list and the "already in application" check
    #    both filter on application_id, and disassociation REMOVEs it — so
    #    without setting it here the association is invisible even though the
    #    request succeeds. Count only *newly* associated use cases so
    #    usecase_count stays accurate when the same use case is added twice.
    newly_added = 0
    for usecase_id in usecase_ids:
        update_expression = 'SET application_id = :app_id'
        expression_values = {':app_id': app_id}
        if owner_team_id:
            update_expression += ', owner_team_id = :owner_team_id'
            expression_values[':owner_team_id'] = owner_team_id
        try:
            resp = table.update_item(
                Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ConditionExpression='attribute_exists(pk)',
                ReturnValues='UPDATED_OLD',
            )
            old_app_id = (resp.get('Attributes') or {}).get('application_id')
            if old_app_id != app_id:
                newly_added += 1
        except Exception:
            logger.warning(f"Could not set application_id on usecase {usecase_id}")

    if newly_added:
        table.update_item(
            Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'},
            UpdateExpression='ADD usecase_count :count',
            ExpressionAttributeValues={':count': newly_added},
        )

    logger.info(
        f"Associated {len(usecase_ids)} usecases with application {app_id} "
        f"({newly_added} newly added)"
    )
    return create_response(200, {'status': 'usecases associated', 'count': len(usecase_ids)})


def _remove_usecases(table, app_id: str, usecase_ids: list) -> Dict[str, Any]:
    with table.batch_writer() as batch:
        for usecase_id in usecase_ids:
            batch.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': f'USECASE#{usecase_id}'})

    # Clear application_id, counting only use cases that were actually
    # associated so usecase_count doesn't drift on repeat removes.
    removed = 0
    for usecase_id in usecase_ids:
        try:
            resp = table.update_item(
                Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'},
                UpdateExpression='REMOVE application_id',
                ConditionExpression='attribute_exists(pk)',
                ReturnValues='UPDATED_OLD',
            )
            if (resp.get('Attributes') or {}).get('application_id') is not None:
                removed += 1
        except Exception:
            logger.warning(f"Could not clear application_id from usecase {usecase_id}")

    if removed:
        table.update_item(
            Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'},
            UpdateExpression='ADD usecase_count :dec',
            ExpressionAttributeValues={':dec': -removed},
        )

    logger.info(
        f"Removed {len(usecase_ids)} usecases from application {app_id} "
        f"({removed} cleared)"
    )
    return create_response(200, {'status': 'usecases removed', 'count': len(usecase_ids)})
