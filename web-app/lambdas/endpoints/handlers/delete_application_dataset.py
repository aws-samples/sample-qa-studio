import lambda_init  # noqa: F401 — must be first import (pydantic)
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, validate_path_id, no_content_response
from resource_auth import require_resource_access, app_from_path
from dataset_models import DATASET_NOT_FOUND_ERROR, dataset_sk, get_dataset
from dataset_usage import find_dataset_references

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DATASET_REFERENCED_ERROR = 'dataset is referenced by repeat steps of this application; remove the references first'


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELETE /applications/{id}/datasets/{datasetId} — 204, or 409 with the
    referencing use cases (``{error, usecases: [{usecase_id, name}]}``).
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path
    dataset_id, error_response = validate_path_id(event['pathParameters'].get('datasetId'), 'dataset ID')
    if error_response:
        return error_response

    table = boto3.resource('dynamodb').Table(get_table_name())
    if get_dataset(table, app_id, dataset_id) is None:
        return create_response(404, {'error': DATASET_NOT_FOUND_ERROR})

    references = find_dataset_references(table, app_id, dataset_id)
    if references:
        return create_response(409, {'error': DATASET_REFERENCED_ERROR, 'usecases': references})

    table.delete_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': dataset_sk(dataset_id)})
    logger.info(f"Deleted dataset {dataset_id} from application {app_id}")
    return no_content_response()
