import lambda_init  # noqa: F401 — must be first import (pydantic)
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name
from resource_auth import require_resource_access, app_from_path
from dataset_models import ApplicationDataset, list_datasets

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', app_from_path, scopes=['api/applications.read'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /applications/{id}/datasets — summary rows (no columns / rows), sorted by name.
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path

    table = boto3.resource('dynamodb').Table(get_table_name())
    datasets = [ApplicationDataset.from_item(item).summary() for item in list_datasets(table, app_id)]
    return create_response(200, {'datasets': datasets})
