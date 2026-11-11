import lambda_init  # noqa: F401 — must be first import (pydantic)
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, validate_path_id, get_current_timestamp
from resource_auth import require_resource_access, app_from_path
from dataset_models import (
    DATASET_NOT_FOUND_ERROR,
    ApplicationDataset,
    ApplicationDatasetUpdate,
    dataset_name_conflict_error,
    find_name_conflict,
    get_dataset,
    list_datasets,
    parse_dataset_request,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /applications/{id}/datasets/{datasetId} — full replace; 200 {dataset}.

    Keeps ``dataset_id`` / ``created_at`` / ``created_by``; 400 {errors} on
    validation, 409 when the new name belongs to another dataset of the app.
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path
    dataset_id, error_response = validate_path_id(event['pathParameters'].get('datasetId'), 'dataset ID')
    if error_response:
        return error_response

    table = boto3.resource('dynamodb').Table(get_table_name())
    current = get_dataset(table, app_id, dataset_id)
    if current is None:
        return create_response(404, {'error': DATASET_NOT_FOUND_ERROR})

    request, error_response = parse_dataset_request(event, ApplicationDatasetUpdate)
    if error_response:
        return error_response

    if find_name_conflict(list_datasets(table, app_id), request.name, exclude_dataset_id=dataset_id):
        return create_response(409, {'error': dataset_name_conflict_error(request.name)})

    existing = ApplicationDataset.from_item(current)
    dataset = existing.model_copy(update={
        'name': request.name,
        'description': request.description,
        'columns': request.columns,
        'rows': request.rows,
        'updated_at': get_current_timestamp(),
    })
    table.put_item(Item=dataset.to_item(app_id))

    logger.info(f"Updated dataset {dataset_id} in application {app_id}")
    return create_response(200, {'dataset': dataset.model_dump()})
