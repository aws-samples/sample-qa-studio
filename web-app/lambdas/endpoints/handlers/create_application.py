import json
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, require_scopes, generate_uuid7, get_current_timestamp

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ['api/applications.write'])
    if error_response:
        return error_response

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    name = body.get('name', '').strip()
    base_url = body.get('base_url', '').strip()

    if not name:
        return create_response(400, {'error': 'name is required'})
    if not base_url:
        return create_response(400, {'error': 'base_url is required'})

    app_id = generate_uuid7()
    now = get_current_timestamp()

    application = {
        'pk': f'APPLICATION#{app_id}',
        'sk': 'METADATA',
        'id': app_id,
        'name': name,
        'base_url': base_url,
        'description': body.get('description', ''),
        'team': body.get('team', ''),
        'environments': body.get('environments', []),
        'created_at': now,
        'updated_at': now,
        'last_execution_id': '',
        'last_execution_status': '',
        'last_execution_at': '',
        'usecase_count': 0,
    }

    index_record = {
        'pk': 'APPLICATIONS',
        'sk': f'APPLICATION#{app_id}',
        'id': app_id,
        'name': name,
    }

    dynamodb = boto3.client('dynamodb')
    table_name = get_table_name()

    def to_dynamo(item: dict) -> dict:
        result = {}
        for k, v in item.items():
            if isinstance(v, str):
                result[k] = {'S': v}
            elif isinstance(v, bool):
                result[k] = {'BOOL': v}
            elif isinstance(v, int):
                result[k] = {'N': str(v)}
            elif isinstance(v, list):
                result[k] = {'L': [{'S': i} for i in v]}
        return result

    dynamodb.transact_write_items(
        TransactItems=[
            {'Put': {'TableName': table_name, 'Item': to_dynamo(application)}},
            {'Put': {'TableName': table_name, 'Item': to_dynamo(index_record)}},
        ]
    )

    logger.info(f"Created application {app_id}")
    return create_response(201, application)
