"""Shared builder for EXECUTION_STEP# records.

``execute_usecase`` and ``execute_test_suite`` both turn a usecase's STEP#
records into EXECUTION_STEP# records when an execution is created.  This
module is the single home of that logic:

- ``build_execution_step_items`` resolves ``dataset_id`` references
  (``dataset_ref``), unrolls repeat steps (``repeat_expansion``) and copies
  the agreed field list (and nothing else) from each step onto a new
  EXECUTION_STEP# item, preserving ``sort`` order.
- ``write_execution_step_items`` persists the items with
  ``batch_write_item`` in chunks of 25, retrying unprocessed items.

Both functions work in the low-level ``boto3.client('dynamodb')`` typed
attribute format (``{'S': ...}``), which is what both callers use; the
resolution and expansion themselves run on plain dicts (see
``dataset_ref`` / ``repeat_expansion``).
"""
import time
from typing import Any, Dict, List, Optional

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from dataset_ref import DatasetFetcher, DatasetNotFoundError, resolve_dataset_refs  # noqa: F401  (re-exported)
from repeat_expansion import RepeatExpansionError, expand_repeat_steps  # noqa: F401  (re-exported)
from repeat_validation import REPEAT_STEP_TYPE
from step_copy import COPYABLE_STEP_FIELDS, STEP_RUNTIME_FIELDS
from utils import generate_uuid7

#: Definition fields that are *not* copied onto an EXECUTION_STEP#: the repeat
#: dataset (inline rows or the ``dataset_id`` reference) is expanded into
#: per-row children instead, ``value_step`` is legacy.
_NOT_COPIED_TO_EXECUTION = ('repeat_columns', 'repeat_rows', 'dataset_id', 'value_step')

# Fields copied verbatim from a STEP# record onto its EXECUTION_STEP# record
# when present: every authored field (``step_copy``) plus the runtime state.
# Both execute Lambdas and the network_assertion propagation test rely on it.
COPIED_STEP_FIELDS = tuple(
    f for f in COPYABLE_STEP_FIELDS if f not in _NOT_COPIED_TO_EXECUTION
) + STEP_RUNTIME_FIELDS

#: Fields added by ``repeat_expansion`` to expanded children.
REPEAT_EXPANSION_FIELDS = (
    'repeat_step_id', 'repeat_label', 'repeat_row_index', 'repeat_row_total', 'row_variables',
)

_REQUIRED_STEP_FIELDS = ('id', 'sort', 'instruction', 'step_type')

_BATCH_SIZE = 25
_MAX_BATCH_RETRIES = 5


def _has_repeat(steps: List[Dict[str, Any]]) -> bool:
    for step in steps:
        if step.get('step_type', {}).get('S') == REPEAT_STEP_TYPE:
            return True
        if 'parent_step_id' in step:
            return True
    return False


def _no_application(dataset_id: str) -> None:
    """Fetcher for callers without an application context: nothing resolves."""
    return None


def _expand_typed_steps(
    steps: List[Dict[str, Any]],
    dataset_overrides: Optional[Dict[str, Dict[str, Any]]],
    dataset_fetcher: Optional[DatasetFetcher],
) -> List[Dict[str, Any]]:
    """Resolve dataset references and run ``expand_repeat_steps`` on typed STEP# records.

    Usecases without a repeat step skip the round trip entirely so their
    records stay byte-for-byte identical to the pre-repeat behaviour
    (including their original ``sort`` values).  Only repeat steps carry
    ``dataset_id``, so the fetcher is never consulted on that path either.
    """
    if not _has_repeat(steps) and not dataset_overrides:
        return steps
    deserializer = TypeDeserializer()
    serializer = TypeSerializer()
    plain = [
        {k: deserializer.deserialize(v) for k, v in step.items()}
        for step in steps
    ]
    for step in plain:
        if 'sort' in step:
            step['sort'] = int(step['sort'])
    plain = resolve_dataset_refs(plain, dataset_fetcher or _no_application)
    expanded = expand_repeat_steps(plain, dataset_overrides)
    return [
        {k: serializer.serialize(v) for k, v in step.items()}
        for step in expanded
    ]


def build_execution_step_items(
    steps: List[Dict[str, Any]],
    execution_id: str,
    created_at: str,
    dataset_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    dataset_fetcher: Optional[DatasetFetcher] = None,
) -> List[Dict[str, Any]]:
    """Return EXECUTION_STEP# items for ``steps`` (DynamoDB typed format).

    ``steps`` are STEP# records as returned by the low-level client.  Repeat
    steps that reference an application dataset are resolved first through
    ``dataset_fetcher`` (``dataset_ref.application_dataset_fetcher`` bound to
    the use case's application; without one every reference raises
    ``DatasetNotFoundError``).  Repeats are then unrolled
    (``repeat_expansion``; ``dataset_overrides`` replaces stored *or*
    resolved rows by repeat label, so the CLI layer wins) — this raises
    ``RepeatExpansionError``.  Callers map both errors to a 400 *before*
    writing anything.  Items are sorted by their numeric ``sort`` attribute;
    every item gets a fresh UUIDv7 sort key.  ``id`` is copied as ``step_id``.
    """
    steps = _expand_typed_steps(steps, dataset_overrides, dataset_fetcher)
    ordered = sorted(steps, key=lambda s: int(s.get('sort', {}).get('N', '0')))
    items: List[Dict[str, Any]] = []
    for step in ordered:
        item: Dict[str, Any] = {
            'pk': {'S': f'EXECUTION#{execution_id}'},
            'sk': {'S': f'EXECUTION_STEP#{generate_uuid7()}'},
            'created_at': {'S': created_at},
        }
        if 'id' in step:
            item['step_id'] = step['id']
        for field in _REQUIRED_STEP_FIELDS[1:]:
            if field in step:
                item[field] = step[field]
        for field in COPIED_STEP_FIELDS + REPEAT_EXPANSION_FIELDS:
            if field in step:
                item[field] = step[field]
        items.append(item)
    return items


def write_execution_step_items(dynamodb, table_name: str, items: List[Dict[str, Any]]) -> None:
    """Persist ``items`` with ``batch_write_item`` (25 per call).

    Unprocessed items are retried with exponential back-off; after
    ``_MAX_BATCH_RETRIES`` attempts a ``RuntimeError`` is raised so the
    caller fails loudly instead of leaving a partially written execution.
    """
    for start in range(0, len(items), _BATCH_SIZE):
        chunk = items[start:start + _BATCH_SIZE]
        request_items = {table_name: [{'PutRequest': {'Item': item}} for item in chunk]}
        attempt = 0
        while request_items:
            response = dynamodb.batch_write_item(RequestItems=request_items)
            unprocessed = response.get('UnprocessedItems') if isinstance(response, dict) else None
            request_items = {k: v for k, v in (unprocessed or {}).items() if v}
            if not request_items:
                break
            attempt += 1
            if attempt > _MAX_BATCH_RETRIES:
                raise RuntimeError(
                    f'batch_write_item left {sum(len(v) for v in request_items.values())} '
                    f'execution steps unprocessed after {_MAX_BATCH_RETRIES} retries'
                )
            print(f'batch_write_item returned unprocessed items, retry {attempt}/{_MAX_BATCH_RETRIES}')
            time.sleep(0.1 * (2 ** (attempt - 1)))
