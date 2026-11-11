import lambda_init  # noqa: F401 — must be first import (pydantic)
import logging
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, extract_user_identity, generate_uuid7, get_current_timestamp
from resource_auth import require_resource_access, app_from_path
from dataset_models import (
    ApplicationDataset,
    ApplicationDatasetCreate,
    dataset_name_conflict_error,
    find_name_conflict,
    list_datasets,
    parse_dataset_request,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', app_from_path, scopes=['api/applications.write'])
def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /applications/{id}/datasets — create a dataset; 201 {dataset}.

    400 {errors} on validation (same strings as inline repeats), 409 when a
    dataset of that name (case-insensitive) already exists in the application.
    """
    app_id = event['pathParameters']['id']  # validated by app_from_path

    request, error_response = parse_dataset_request(event, ApplicationDatasetCreate)
    if error_response:
        return error_response

    table = boto3.resource('dynamodb').Table(get_table_name())
    if find_name_conflict(list_datasets(table, app_id), request.name):
        return create_response(409, {'error': dataset_name_conflict_error(request.name)})

    now = get_current_timestamp()
    dataset = ApplicationDataset(
        dataset_id=generate_uuid7(),
        name=request.name,
        description=request.description,
        columns=request.columns,
        rows=request.rows,
        created_at=now,
        updated_at=now,
        created_by=extract_user_identity(event).get('identity', ''),
    )
    table.put_item(Item=dataset.to_item(app_id))

    logger.info(f"Created dataset {dataset.dataset_id} in application {app_id}")
    return create_response(201, {'dataset': dataset.model_dump()})
