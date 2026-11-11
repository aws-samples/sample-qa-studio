import logging
from typing import Any, Dict
import boto3
from resource_auth import require_resource_access, app_from_path
from utils import create_response, get_table_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', app_from_path, scopes=['api/applications.read'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /applications/{id}/variables — the application-level variable list
    (``APPLICATION#{id} / VARIABLES``), inherited by every use case of the
    application. ``[]`` when the record does not exist.
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(get_table_name())
    item = table.get_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': 'VARIABLES'}).get('Item')
    variables = [
        {'key': variable['key'], 'value': variable['value']}
        for variable in (item or {}).get('variables', [])
    ]
    return create_response(200, {'variables': variables})
