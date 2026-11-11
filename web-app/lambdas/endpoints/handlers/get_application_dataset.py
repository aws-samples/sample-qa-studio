import lambda_init  # noqa: F401 — must be first import (pydantic)
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, validate_path_id
from resource_auth import require_resource_access, app_from_path
from dataset_models import DATASET_NOT_FOUND_ERROR, ApplicationDataset, get_dataset

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('view', app_from_path, scopes=['api/applications.read'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /applications/{id}/datasets/{datasetId} — the full dataset (columns and rows).
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path
    dataset_id, error_response = validate_path_id(event['pathParameters'].get('datasetId'), 'dataset ID')
    if error_response:
        return error_response

    table = boto3.resource('dynamodb').Table(get_table_name())
    item = get_dataset(table, app_id, dataset_id)
    if item is None:
        return create_response(404, {'error': DATASET_NOT_FOUND_ERROR})
    return create_response(200, {'dataset': ApplicationDataset.from_item(item).model_dump()})
