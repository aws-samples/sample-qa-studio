import logging
from typing import Any, Dict
import boto3
from resource_auth import require_resource_access, app_from_path
from utils import create_response, get_table_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', app_from_path, scopes=['api/applications.read'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    app_id = event['pathParameters']['id']
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())
    response = table.get_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': 'METADATA'})
    item = response.get('Item')
    if not item:
        return create_response(404, {'error': 'Application not found'})
    item.pop('pk', None)
    item.pop('sk', None)
    return create_response(200, item)
