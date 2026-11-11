import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import boto3
from utils import create_response, get_table_name, validate_path_id, get_current_timestamp
from resource_auth import require_resource_access, app_from_path, authorize_resource, owner_of
from dataset_usage import find_usecase_dataset_steps
import permissions_repo

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USECASE_REFERENCES_DATASETS_ERROR = 'use case references application datasets'


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add or remove use cases on an application.

    Requires edit on the target app (decorator) and edit on each use case's
    current app, so nobody can pull in or detach another team's use cases.
    Moving a use case in from another application is refused with ``409``
    while any of its steps references a dataset (datasets belong to the
    application being left; variables and secrets move silently).
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

    moving_ids, usecase_err = _authorize_current_apps(event, app_id, usecase_ids)
    if usecase_err:
        return usecase_err

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    if action == 'remove':
        return _remove_usecases(table, app_id, usecase_ids)

    blocked = _usecases_referencing_datasets(table, moving_ids)
    if blocked:
        logger.info(
            f"Refused moving {len(blocked)} usecases into application {app_id}: dataset references"
        )
        return create_response(409, {'error': USECASE_REFERENCES_DATASETS_ERROR, 'usecases': blocked})

    return _add_usecases(
        table, app_id, usecase_ids, body.get('environment', ''),
        permissions_repo.get_app_owner(app_id),
    )


def _authorize_current_apps(event: Dict[str, Any], app_id: str,
                            usecase_ids: list) -> Tuple[List[str], Optional[Dict[str, Any]]]:
    """
    Require edit on the app each use case currently belongs to. Use cases
    already in `app_id` are covered by the decorator; orphaned use cases
    (no app) are admin-only.

    Returns:
        ``(moving_ids, None)`` when allowed — ``moving_ids`` are the use cases
        not currently in ``app_id`` — otherwise ``([], response)`` with a
        400/403/404 response.
    """
    moving_ids: List[str] = []
    for usecase_id in usecase_ids:
        _, err = validate_path_id(usecase_id if isinstance(usecase_id, str) else None, 'usecase ID')
        if err:
            return [], err
        owner = permissions_repo.get_usecase_owner(usecase_id)
        if owner is None:
            return [], create_response(404, {'error': f'Use case {usecase_id} not found'})
        current_app_id, current_owner = owner_of(owner)
        if current_app_id == app_id:
            continue
        _, auth_err = authorize_resource(event, current_app_id or '', 'edit',
                                         owner_team_id=current_owner)
        if auth_err:
            return [], auth_err
        moving_ids.append(usecase_id)
    return moving_ids, None


def _usecases_referencing_datasets(table, moving_ids: List[str]) -> List[Dict[str, Any]]:
    """
    The 409 body entries for the moved use cases whose steps reference a
    dataset (``[{usecase_id, name, steps: [{id, instruction}]}]``), sorted by
    name. Empty when the move is allowed.
    """
    blocked = []
    for usecase_id in moving_ids:
        reference = find_usecase_dataset_steps(table, usecase_id)
        if reference:
            blocked.append(reference)
    blocked.sort(key=lambda ref: (ref['name'].lower(), ref['usecase_id']))
    return blocked


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
