import json
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, require_scopes, validate_path_id, get_current_timestamp

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ['api/applications.write'])
    if error_response:
        return error_response

    app_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'application ID')
    if error:
        return error

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    usecase_ids = body.get('usecase_ids', [])
    action = body.get('action', 'add')

    if not usecase_ids or not isinstance(usecase_ids, list):
        return create_response(400, {'error': 'usecase_ids must be a non-empty list'})

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    if action == 'remove':
        return _remove_usecases(table, app_id, usecase_ids)

    return _add_usecases(table, app_id, usecase_ids, body.get('environment', ''))


def _add_usecases(table, app_id: str, usecase_ids: list, environment: str) -> Dict[str, Any]:
    now = get_current_timestamp()

    with table.batch_writer() as batch:
        for usecase_id in usecase_ids:
            batch.put_item(Item={
                'pk': f'APPLICATION#{app_id}',
                'sk': f'USECASE#{usecase_id}',
                'associated_at': now,
                'environment': environment,
            })

    for usecase_id in usecase_ids:
        try:
            table.update_item(
                Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'},
                UpdateExpression='SET application_id = :app_id',
                ExpressionAttributeValues={':app_id': app_id},
                ConditionExpression='attribute_exists(pk)',
            )
        except Exception:
            logger.warning(f"Could not set application_id on usecase {usecase_id}")

    table.update_item(
        Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'},
        UpdateExpression='ADD usecase_count :count',
        ExpressionAttributeValues={':count': len(usecase_ids)},
    )

    logger.info(f"Associated {len(usecase_ids)} usecases with application {app_id}")
    return create_response(200, {'status': 'usecases associated', 'count': len(usecase_ids)})


def _remove_usecases(table, app_id: str, usecase_ids: list) -> Dict[str, Any]:
    with table.batch_writer() as batch:
        for usecase_id in usecase_ids:
            batch.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': f'USECASE#{usecase_id}'})

    for usecase_id in usecase_ids:
        try:
            table.update_item(
                Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'},
                UpdateExpression='REMOVE application_id',
                ConditionExpression='attribute_exists(pk)',
            )
        except Exception:
            logger.warning(f"Could not clear application_id from usecase {usecase_id}")

    table.update_item(
        Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'},
        UpdateExpression='ADD usecase_count :dec',
        ExpressionAttributeValues={':dec': -len(usecase_ids)},
    )

    logger.info(f"Removed {len(usecase_ids)} usecases from application {app_id}")
    return create_response(200, {'status': 'usecases removed', 'count': len(usecase_ids)})
