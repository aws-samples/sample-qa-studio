"""Validation rules for ``repeat`` steps and ``parent_step_id`` children.

Shared by ``create_step``, ``update_step``, ``import_usecase`` and the
execute Lambdas (dataset overrides).  The CLI mirrors these rules in
``qa_studio_cli/validation.py`` (``validate_repeat_step``) — keep the two in
lockstep; error strings are compared in the parity tests.

A repeat is an ordinary STEP# record with ``step_type == "repeat"`` plus
exactly one dataset source:

- ``dataset_id``: an application dataset (``APPLICATION#{app} / DATASET#{id}``,
  see ``dataset_models``), resolved into columns / rows at execution time; or
- inline ``repeat_columns`` / ``repeat_rows``:
  - ``repeat_columns``: 1–20 identifiers (``^[A-Za-z_][A-Za-z0-9_]*$``), unique,
    not a reserved built-in name.
  - ``repeat_rows``: 1–100 rows, each exactly ``len(repeat_columns)`` string cells.
  - ``json.dumps(columns) + json.dumps(rows)`` ≤ 200 KB.

Both or neither is a validation error (``REPEAT_BOTH_SOURCES_ERROR`` /
``REPEAT_NO_SOURCE_ERROR``).  ``instruction`` (the label) is unique among the
usecase's repeat steps.  Whether the referenced dataset *exists* is checked by
the step write Lambdas, not here (it needs the use case's application).

A child is any non-repeat step with ``parent_step_id`` pointing at a repeat
that itself has no parent (one nesting level).
"""
import json
import re
from typing import Any, Dict, List, Optional

MAX_REPEAT_COLUMNS = 20
MAX_REPEAT_ROWS = 100
MAX_REPEAT_DATASET_BYTES = 200 * 1024

#: Built-in template names a dataset column may not shadow.
RESERVED_COLUMN_NAMES = frozenset({
    'UniqueID', 'Time', 'ExecutionID', 'CreatedAt', 'RepeatIndex', 'RepeatTotal',
})

_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

REPEAT_STEP_TYPE = 'repeat'

#: Dataset-source rule (mirrored verbatim by the CLI).
REPEAT_NO_SOURCE_ERROR = 'repeat step must have either dataset_id or repeat_columns/repeat_rows'
REPEAT_BOTH_SOURCES_ERROR = 'repeat step cannot have both dataset_id and inline rows'


def has_dataset_reference(step: Dict[str, Any]) -> bool:
    """True when ``step`` names an application dataset (non-empty ``dataset_id``)."""
    dataset_id = step.get('dataset_id')
    return dataset_id is not None and dataset_id != ''


def present_repeat_only_fields(step: Dict[str, Any]) -> List[str]:
    """The repeat-only fields ``step`` carries (``dataset_id`` counts only when non-empty)."""
    present = [f for f in ('repeat_columns', 'repeat_rows') if step.get(f) is not None]
    if has_dataset_reference(step):
        present.append('dataset_id')
    return present


def validate_repeat_columns(columns: Any) -> List[str]:
    """Rules for ``repeat_columns`` alone (also used for dataset overrides)."""
    errors: List[str] = []
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        return ['repeat_columns must be a list of strings']
    if len(columns) < 1:
        errors.append('repeat_columns must contain at least 1 column')
    if len(columns) > MAX_REPEAT_COLUMNS:
        errors.append(f'repeat_columns must contain at most {MAX_REPEAT_COLUMNS} columns')
    for column in columns:
        if not _IDENTIFIER_RE.match(column):
            errors.append(
                f'repeat column "{column}" is not a valid identifier '
                f'(letters, digits and underscores, not starting with a digit)'
            )
        elif column in RESERVED_COLUMN_NAMES:
            errors.append(f'repeat column "{column}" is a reserved name')
    if len(set(columns)) != len(columns):
        errors.append('repeat_columns must be unique')
    return errors


def validate_repeat_rows(rows: Any, column_count: int) -> List[str]:
    """Rules for ``repeat_rows`` given the number of columns."""
    errors: List[str] = []
    if not isinstance(rows, list):
        return ['repeat_rows must be a list of rows']
    if len(rows) < 1:
        errors.append('repeat_rows must contain at least 1 row')
    if len(rows) > MAX_REPEAT_ROWS:
        errors.append(f'repeat_rows must contain at most {MAX_REPEAT_ROWS} rows')
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            errors.append(f'repeat_rows row {index} must be a list of cells')
            continue
        if len(row) != column_count:
            errors.append(
                f'repeat_rows row {index} has {len(row)} cells but {column_count} cells are expected'
            )
        if not all(isinstance(cell, str) for cell in row):
            errors.append(f'repeat_rows row {index} must contain only string cells')
    return errors


def validate_dataset_size(columns: Any, rows: Any) -> List[str]:
    """Serialized ``columns + rows`` must stay under the 200 KB cap."""
    try:
        size = len(json.dumps(columns)) + len(json.dumps(rows))
    except (TypeError, ValueError):
        return ['repeat dataset is not JSON serializable']
    if size > MAX_REPEAT_DATASET_BYTES:
        return [
            f'repeat dataset is too large ({size} bytes; the limit is '
            f'{MAX_REPEAT_DATASET_BYTES} bytes / 200 KB)'
        ]
    return []


def validate_dataset(columns: Any, rows: Any) -> List[str]:
    """Validate a ``{columns, rows}`` pair (stored dataset or override)."""
    errors = validate_repeat_columns(columns)
    if isinstance(columns, list):
        errors.extend(validate_repeat_rows(rows, len(columns)))
    elif rows is not None and not isinstance(rows, list):
        errors.append('repeat_rows must be a list of rows')
    if not errors:
        errors.extend(validate_dataset_size(columns, rows))
    return errors


def validate_repeat_source(step: Dict[str, Any]) -> List[str]:
    """The dataset-source rule of a repeat step: ``dataset_id`` XOR inline rows.

    Mirrored by ``qa_studio_cli.validation.validate_repeat_step`` — same
    checks in the same order, same strings.
    """
    errors: List[str] = []
    columns = step.get('repeat_columns')
    rows = step.get('repeat_rows')
    has_inline = columns is not None or rows is not None
    if has_dataset_reference(step):
        if not isinstance(step.get('dataset_id'), str):
            errors.append('dataset_id must be a string')
        if has_inline:
            errors.append(REPEAT_BOTH_SOURCES_ERROR)
        return errors
    if not has_inline:
        return [REPEAT_NO_SOURCE_ERROR]
    if columns is None:
        errors.append('repeat_columns is required for repeat steps')
    if rows is None:
        errors.append('repeat_rows is required for repeat steps')
    if columns is not None and rows is not None:
        errors.extend(validate_dataset(columns, rows))
    return errors


def _find_step(steps: List[Dict[str, Any]], step_id: Optional[str]) -> Optional[Dict[str, Any]]:
    for step in steps:
        if step.get('id') == step_id:
            return step
    return None


def validate_repeat_fields(step: Dict[str, Any], existing_steps: List[Dict[str, Any]]) -> List[str]:
    """Validate the repeat-related fields of ``step`` against its siblings.

    ``step`` and ``existing_steps`` are plain dicts (resource-API shape, no
    DynamoDB type wrappers).  ``existing_steps`` may include ``step`` itself
    (update path) — it is matched by ``id`` and ignored for the label check.
    Returns a list of human-readable errors; empty means valid.
    """
    errors: List[str] = []
    step_type = step.get('step_type')
    is_repeat = step_type == REPEAT_STEP_TYPE
    parent_step_id = step.get('parent_step_id')

    if is_repeat:
        if parent_step_id:
            errors.append('a repeat step may not have a parent_step_id (nested repeats are not supported)')
        errors.extend(validate_repeat_source(step))
        label = step.get('instruction')
        for other in existing_steps:
            if other.get('id') == step.get('id'):
                continue
            if other.get('step_type') == REPEAT_STEP_TYPE and other.get('instruction') == label:
                errors.append(f'repeat label "{label}" must be unique among the repeat steps of this usecase')
                break
    else:
        for field in present_repeat_only_fields(step):
            errors.append(f'{field} is only allowed on repeat steps')

    if parent_step_id is not None and parent_step_id != '' and not is_repeat:
        if not isinstance(parent_step_id, str):
            errors.append('parent_step_id must be a string')
        else:
            parent = _find_step(existing_steps, parent_step_id)
            if parent is None:
                errors.append(f'parent_step_id "{parent_step_id}" does not exist in this usecase')
            elif parent.get('step_type') != REPEAT_STEP_TYPE:
                errors.append(f'parent_step_id "{parent_step_id}" is not a repeat step')
            elif parent.get('parent_step_id'):
                errors.append('repeat steps support one level of nesting only')

    return errors


def load_usecase_steps(table, usecase_id: str) -> List[Dict[str, Any]]:
    """Return every STEP# record of ``usecase_id`` (resource-API ``Table``).

    Used by the step CRUD Lambdas to load siblings for parent / label checks
    and the delete cascade.  Same query as ``list_steps``.
    """
    from boto3.dynamodb.conditions import Key

    response = table.query(
        KeyConditionExpression=Key('pk').eq(f'USECASE#{usecase_id}') & Key('sk').begins_with('STEP#')
    )
    return response.get('Items', [])


def needs_sibling_validation(step: Dict[str, Any]) -> bool:
    """True when ``step`` carries any repeat-related field worth a sibling query."""
    return (
        step.get('step_type') == REPEAT_STEP_TYPE
        or bool(step.get('parent_step_id'))
        or bool(present_repeat_only_fields(step))
    )


def children_of(steps: List[Dict[str, Any]], repeat_id: str) -> List[Dict[str, Any]]:
    """Children of the repeat ``repeat_id`` in ``sort`` order."""
    children = [s for s in steps if s.get('parent_step_id') == repeat_id]
    children.sort(key=lambda s: int(s.get('sort', 0)))
    return children


#: Templates have no nesting model yet; the frontend reuses this text.
REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR = 'repeat steps are not supported in templates'


def template_step_repeat_error(body: Dict[str, Any]) -> Optional[str]:
    """Return the 400 message when a template-step body carries repeat fields."""
    if body.get('step_type') == REPEAT_STEP_TYPE or body.get('parent_step_id'):
        return REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR
    return None


#: Templates have no application, so there is no dataset a step could reference.
DATASET_NOT_SUPPORTED_IN_TEMPLATES_ERROR = 'dataset references (dataset_id) are not supported in templates'


def template_step_dataset_error(body: Dict[str, Any]) -> Optional[str]:
    """Return the 400 message when a template-step body carries ``dataset_id``."""
    if has_dataset_reference(body):
        return DATASET_NOT_SUPPORTED_IN_TEMPLATES_ERROR
    return None


def template_step_error(body: Dict[str, Any]) -> Optional[str]:
    """First 400 message of the template-step guards (repeat shape, dataset reference)."""
    return template_step_repeat_error(body) or template_step_dataset_error(body)
