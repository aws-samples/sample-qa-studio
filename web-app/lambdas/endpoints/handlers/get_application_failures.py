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
        query_params = event.get('queryStringParameters') or {}
        limit = min(int(query_params.get('limit', '10')), 50)

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        response = table.query(
            KeyConditionExpression=Key('pk').eq(f'APPLICATION_FAILURES#{app_id}'),
            ScanIndexForward=False,
            Limit=limit,
        )

        failures = response.get('Items', [])
        for item in failures:
            item.pop('pk', None)

        return create_response(200, failures)
    except Exception as e:
        logger.error(f"Error fetching failures for app {app_id}: {e}", exc_info=True)
        return create_response(500, {'error': f'Failed to fetch failures: {str(e)}'})
