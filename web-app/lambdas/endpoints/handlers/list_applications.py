import logging
from typing import Any, Dict
import boto3
from boto3.dynamodb.conditions import Key
from utils import create_response, get_table_name, require_scopes

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ['api/applications.read'])
    if error_response:
        return error_response

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    index_response = table.query(
        KeyConditionExpression=Key('pk').eq('APPLICATIONS') & Key('sk').begins_with('APPLICATION#')
    )

    app_ids = [item['id'] for item in index_response.get('Items', [])]

    if not app_ids:
        return create_response(200, [])

    keys = [{'pk': f'APPLICATION#{aid}', 'sk': 'METADATA'} for aid in app_ids]

    response = dynamodb.batch_get_item(
        RequestItems={get_table_name(): {'Keys': keys}}
    )

    applications = response.get('Responses', {}).get(get_table_name(), [])

    for app in applications:
        app.pop('pk', None)
        app.pop('sk', None)

    return create_response(200, applications)
