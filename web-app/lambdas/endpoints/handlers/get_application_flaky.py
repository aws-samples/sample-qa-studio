import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, require_scopes, validate_path_id

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ['api/applications.read'])
    if error_response:
        return error_response

    app_id, error = validate_path_id(event.get('pathParameters', {}).get('id'), 'application ID')
    if error:
        return error

    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'APPLICATION_FLAKY#{app_id}')
        )

        items = [item for item in response.get('Items', []) if item.get('flip_count_7d', 0) > 0]
        items.sort(key=lambda x: x.get('flip_count_7d', 0), reverse=True)

        for item in items:
            item.pop('pk', None)

        return create_response(200, items)
    except Exception as e:
        logger.error(f"Error fetching flaky usecases for app {app_id}: {e}", exc_info=True)
        return create_response(500, {'error': f'Failed to fetch flaky usecases: {str(e)}'})
