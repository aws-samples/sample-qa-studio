import json
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, extract_user_identity, get_current_timestamp
from resource_auth import require_resource_access, app_from_path, require_owner_team_lead
from perm_audit import log_permission_change

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an application's metadata.

    Only a Team Lead of the owning team (or a studio admin) may update it;
    shared access never allows it. A base_url change is audit-logged.
    """
    user_identity = extract_user_identity(event)
    app_id = event['pathParameters']['id']  # validated by app_from_path

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())

    current = table.get_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'}).get('Item')
    if not current:
        return create_response(404, {'error': 'Application not found'})
    owner_team_id = current.get('owner_team_id') or None
    role_err = require_owner_team_lead(user_identity, owner_team_id)
    if role_err:
        return role_err

    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

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

    if 'base_url' in body and body['base_url'] != current.get('base_url'):
        log_permission_change(
            actor={'sub': user_identity.get('sub', ''), 'client_id': user_identity.get('client_id', '')},
            action='app_base_url_change',
            target={'app_id': app_id, 'owner_team_id': owner_team_id or ''},
            details={'old': current.get('base_url', ''), 'new': body['base_url']},
        )
    # Update name in index record if changed
    if 'name' in body:
        table.update_item(
            Key={'pk': 'APPLICATIONS', 'sk': f'APPLICATION#{app_id}'},
            UpdateExpression='SET #n = :name',
            ExpressionAttributeNames={'#n': 'name'},
            ExpressionAttributeValues={':name': body['name']},
        )

    return create_response(200, {'status': 'application updated', 'id': app_id})
