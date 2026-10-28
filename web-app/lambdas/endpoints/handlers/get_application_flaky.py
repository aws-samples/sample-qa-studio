import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from resource_auth import require_resource_access, app_from_path
from utils import create_response, get_table_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', app_from_path, scopes=['api/applications.read'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    app_id = event['pathParameters']['id']

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
