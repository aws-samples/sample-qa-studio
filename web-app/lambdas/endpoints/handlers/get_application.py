import logging
from typing import Any, Dict
import boto3
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

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    response = table.get_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'})
    item = response.get('Item')

    if not item:
        return create_response(404, {'error': 'Application not found'})

    item.pop('pk', None)
    item.pop('sk', None)
    return create_response(200, item)
