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

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    update_parts = ['updated_at = :updated_at']
    expr_values: Dict[str, Any] = {':updated_at': get_current_timestamp()}
    expr_names: Dict[str, str] = {}

    field_map = {
        'name': ('#n', ':name'),
        'base_url': ('base_url', ':base_url'),
        'description': ('description', ':description'),
        'team': ('team', ':team'),
        'environments': ('environments', ':environments'),
    }

    for field, (attr, placeholder) in field_map.items():
        if field in body:
            if attr.startswith('#'):
                expr_names[attr] = field
                update_parts.append(f'{attr} = {placeholder}')
            else:
                update_parts.append(f'{attr} = {placeholder}')
            expr_values[placeholder] = body[field]

    update_kwargs: Dict[str, Any] = {
        'Key': {'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'},
        'UpdateExpression': 'SET ' + ', '.join(update_parts),
        'ExpressionAttributeValues': expr_values,
        'ConditionExpression': 'attribute_exists(pk)',
    }
    if expr_names:
        update_kwargs['ExpressionAttributeNames'] = expr_names

    try:
        table.update_item(**update_kwargs)
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return create_response(404, {'error': 'Application not found'})

    # Update name in index record if changed
    if 'name' in body:
        table.update_item(
            Key={'pk': 'APPLICATIONS', 'sk': f'APPLICATION#{app_id}'},
            UpdateExpression='SET #n = :name',
            ExpressionAttributeNames={'#n': 'name'},
            ExpressionAttributeValues={':name': body['name']},
        )

    return create_response(200, {'status': 'application updated', 'id': app_id})
