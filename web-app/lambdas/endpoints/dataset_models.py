"""Application datasets: the ``APPLICATION#{app_id} / DATASET#{dataset_id}`` record.

A dataset is a named ``columns`` + ``rows`` table owned by an application and
referenced by repeat steps through ``dataset_id`` (instead of inline
``repeat_columns`` / ``repeat_rows``).  The table rules are the inline repeat
rules — ``repeat_validation.validate_dataset`` — so the CLI and the UI show
the same error strings for both.

This module holds the request / response models, the validation entry point
the dataset handlers share, and the partition read helpers (same role as
``template_store`` for templates).

Imports pydantic: handlers must ``import lambda_init`` before importing it.
"""
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError, field_validator

from repeat_validation import has_dataset_reference, validate_dataset
from utils import create_response

DATASET_SK_PREFIX = 'DATASET#'

#: Letters, digits, spaces, underscores and hyphens; starts with a letter or
#: underscore; at most 64 characters.
DATASET_NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_ -]{0,63}$')
DATASET_NAME_RULE = (
    'letters, digits, spaces, underscores and hyphens; must start with a letter '
    'or underscore; at most 64 characters'
)

DATASET_NOT_FOUND_ERROR = 'Dataset not found'


def dataset_sk(dataset_id: str) -> str:
    return f'{DATASET_SK_PREFIX}{dataset_id}'


def dataset_name_conflict_error(name: str) -> str:
    return f'a dataset named "{name}" already exists in this application'


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ApplicationDatasetCreate(BaseModel):
    """``POST /applications/{id}/datasets`` body.

    Construct it only after ``validate_dataset_request`` returned no errors:
    the table rules (and their verbatim error strings) live there, this model
    just types the already-valid payload.
    """

    name: str
    description: str = ''
    columns: List[str]
    rows: List[List[str]]

    @field_validator('name', mode='before')
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class ApplicationDatasetUpdate(ApplicationDatasetCreate):
    """``PUT /applications/{id}/datasets/{datasetId}`` body — a full replace, same shape."""


def dataset_name_errors(name: Any) -> List[str]:
    """Rules for the dataset ``name`` (unique-within-application is checked separately)."""
    if name is None or (isinstance(name, str) and not name.strip()):
        return ['name is required']
    if not isinstance(name, str):
        return ['name must be a string']
    if not DATASET_NAME_PATTERN.match(name.strip()):
        return [f'dataset name "{name}" is invalid ({DATASET_NAME_RULE})']
    return []


def validate_dataset_request(body: Any) -> List[str]:
    """Every error of a create / update body; empty means the model can be built.

    Name errors first, then the ``repeat_validation`` errors for ``columns`` /
    ``rows`` verbatim (clients already know those strings from inline repeats).
    """
    if not isinstance(body, dict):
        return ['request body must be a JSON object']
    errors = dataset_name_errors(body.get('name'))
    if not isinstance(body.get('description', ''), str):
        errors.append('description must be a string')
    errors.extend(validate_dataset(body.get('columns'), body.get('rows')))
    return errors


def parse_dataset_request(event: Dict[str, Any], model_cls: Type[ApplicationDatasetCreate]) -> Tuple[
    Optional[ApplicationDatasetCreate], Optional[Dict[str, Any]]
]:
    """Body of ``event`` as ``model_cls``, or the 400 response.

    Validation errors are returned as ``{errors: [...]}`` (verbatim, one per
    rule) plus the joined ``error`` string every other endpoint uses.
    """
    try:
        body = json.loads(event.get('body') or '{}')
    except (json.JSONDecodeError, TypeError):
        return None, create_response(400, {'error': 'Invalid JSON in request body'})
    errors = validate_dataset_request(body)
    if errors:
        return None, create_response(400, {'error': '; '.join(errors), 'errors': errors})
    try:
        return model_cls(**body), None
    except ValidationError as e:  # the rule set above should make this unreachable
        field = '.'.join(str(p) for p in e.errors()[0]['loc'])
        return None, create_response(400, {'error': f'Invalid value for {field}',
                                           'errors': [f'Invalid value for {field}']})


# ---------------------------------------------------------------------------
# Record model
# ---------------------------------------------------------------------------


class ApplicationDataset(BaseModel):
    """The stored dataset without its DynamoDB keys (the API response shape)."""

    dataset_id: str
    name: str
    description: str = ''
    columns: List[str]
    rows: List[List[str]]
    created_at: str
    updated_at: str
    created_by: str = ''

    @classmethod
    def from_item(cls, item: Dict[str, Any]) -> 'ApplicationDataset':
        return cls(**{k: v for k, v in item.items() if k in cls.model_fields})

    def to_item(self, app_id: str) -> Dict[str, Any]:
        return {
            'pk': f'APPLICATION#{app_id}',
            'sk': dataset_sk(self.dataset_id),
            **self.model_dump(),
        }

    def summary(self) -> Dict[str, Any]:
        """The list-row shape: counts instead of the table itself."""
        return {
            'dataset_id': self.dataset_id,
            'name': self.name,
            'description': self.description,
            'column_count': len(self.columns),
            'row_count': len(self.rows),
            'updated_at': self.updated_at,
        }


# ---------------------------------------------------------------------------
# Partition read helpers (resource-API ``Table``)
# ---------------------------------------------------------------------------


def get_dataset(table, app_id: str, dataset_id: str) -> Optional[Dict[str, Any]]:
    """The ``DATASET#`` item of ``dataset_id`` in ``app_id``, or ``None``."""
    response = table.get_item(Key={'pk': f'APPLICATION#{app_id}', 'sk': dataset_sk(dataset_id)})
    return response.get('Item')


def list_datasets(table, app_id: str) -> List[Dict[str, Any]]:
    """Every ``DATASET#`` item of the application, sorted by name (case-insensitive)."""
    from boto3.dynamodb.conditions import Key

    response = table.query(
        KeyConditionExpression=Key('pk').eq(f'APPLICATION#{app_id}') & Key('sk').begins_with(DATASET_SK_PREFIX)
    )
    items = response.get('Items', [])
    return sorted(items, key=lambda item: str(item.get('name', '')).lower())


def find_name_conflict(datasets: List[Dict[str, Any]], name: str,
                       exclude_dataset_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The dataset (other than ``exclude_dataset_id``) whose name equals ``name`` ignoring case."""
    wanted = name.strip().lower()
    for dataset in datasets:
        if exclude_dataset_id is not None and dataset.get('dataset_id') == exclude_dataset_id:
            continue
        if str(dataset.get('name', '')).lower() == wanted:
            return dataset
    return None


# ---------------------------------------------------------------------------
# Step → dataset references (repeat steps carrying ``dataset_id``)
# ---------------------------------------------------------------------------

#: 400 message when a repeat step names a dataset its application does not have.
DATASET_NOT_IN_APPLICATION_ERROR = 'dataset not found in this application'


def usecase_application_id(table, usecase_id: str) -> Optional[str]:
    """``application_id`` of the ``USECASES / USECASE#{id}`` record, or ``None``."""
    item = table.get_item(Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'}).get('Item') or {}
    return item.get('application_id') or None


def referenced_dataset_ids(steps: Iterable[Dict[str, Any]]) -> List[str]:
    """Distinct ``dataset_id`` values of ``steps``, in first-seen order."""
    seen: List[str] = []
    for step in steps:
        if has_dataset_reference(step) and step['dataset_id'] not in seen:
            seen.append(step['dataset_id'])
    return seen


def missing_dataset_ids(table, app_id: Optional[str], dataset_ids: Iterable[str]) -> List[str]:
    """The ids of ``dataset_ids`` that do not exist in ``app_id`` (all of them when ``app_id`` is empty).

    One ``get_item`` per distinct id; callers only invoke this when at least
    one step carries a reference, so inline-only writes read nothing.
    """
    ids = list(dataset_ids)
    if not app_id:
        return ids
    return [dataset_id for dataset_id in ids if get_dataset(table, app_id, dataset_id) is None]


def missing_datasets_response(missing: List[str]) -> Dict[str, Any]:
    """The 400 of ``import_usecase`` / ``clone_usecase`` for unresolved references.

    Same shape as their template-not-found error: ``success``, ``error``,
    ``message`` and the offending ids (``datasetIds``).
    """
    return create_response(400, {
        'success': False,
        'error': DATASET_NOT_IN_APPLICATION_ERROR,
        'message': f"{DATASET_NOT_IN_APPLICATION_ERROR}: {', '.join(missing)}",
        'datasetIds': missing,
    })
