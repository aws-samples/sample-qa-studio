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
