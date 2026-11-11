"""One place for "which step fields are copied" and the nested repeat shape.

Several Lambdas copy a STEP# record field-by-field onto a new record —
``export_usecase`` (to JSON), ``import_usecase`` (from JSON),
``clone_usecase`` (to a new usecase), the template lambdas (template step
↔ usecase step) and the wizard lambdas (body → EXECUTION_STEP# → STEP#).
Their per-site field lists used to drift; ``COPYABLE_STEP_FIELDS`` is the
single list.  Execution-time copying adds ``STEP_RUNTIME_FIELDS`` and lives
in ``execution_steps.COPIED_STEP_FIELDS``.

``test_step_copy_parity.py`` pins ``COPYABLE_STEP_FIELDS`` to the CLI's
``ExportStep`` model and to ``COPIED_STEP_FIELDS`` — add a new step field in
all three places.

Also the export/import tree helpers: the export JSON nests a repeat's
children under the repeat as ``steps: [...]``; import flattens that shape
(and tolerates the flat ``id`` + ``parent_step_id`` shape) back into
STEP# records.
"""
from typing import Any, Dict, List, Optional, Tuple

from repeat_validation import REPEAT_STEP_TYPE

#: Optional per-step fields copied when present and non-empty (``None`` and
#: ``""`` are skipped; booleans such as ``False`` are kept).
COPYABLE_STEP_FIELDS = (
    'secret_key',
    'validation_type', 'validation_operator', 'validation_value',
    'capture_variable', 'assertion_variable',
    'value_type', 'value_format', 'value_source', 'value_step',
    'enable_advanced_click_types',
    'browser_action', 'browser_args',
    'transform_operation', 'transform_args',
    'network_url_pattern', 'network_method', 'network_request_body',
    'network_body_match_type', 'network_mock_response',
    'network_mock_passthrough', 'network_timeout',
    'network_response_body', 'network_response_body_match_type',
    'network_response_status',
    'repeat_columns', 'repeat_rows', 'dataset_id',
)

#: Per-step state written by the runtime (cache / trajectory), never part of
#: the authored definition.  Copied STEP# → EXECUTION_STEP# only.
#: ``cached_steps`` / ``cache_last_updated`` belong to the removed bbox step
#: cache (codebase-health B5): nothing writes them any more.  They stay here
#: for one release so existing records keep round-tripping; drop them in B9.
STEP_RUNTIME_FIELDS = (
    'cached_steps', 'cache_last_updated',
    'trajectory_s3_key', 'trajectory_last_updated',
)


def copy_step_fields(step: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``instruction``, ``step_type`` and every present copyable field.

    Identity (``pk``/``sk``/``id``), ``sort``, ``parent_step_id``,
    timestamps and the trajectory/cache fields are *not* copied — the
    caller decides those.
    """
    copied: Dict[str, Any] = {
        'instruction': step.get('instruction', ''),
        'step_type': step.get('step_type', ''),
    }
    for field in COPYABLE_STEP_FIELDS:
        value = step.get(field)
        if value is None or value == '':
            continue
        copied[field] = value
    return copied


def _sort_value(step: Dict[str, Any]) -> int:
    try:
        return int(step.get('sort', 0))
    except (TypeError, ValueError):
        return 0


def nest_repeat_children(flat_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Export shape: children under their repeat as ``steps``, in ``sort`` order.

    ``flat_steps`` are export dicts that still carry ``id`` /
    ``parent_step_id``; both keys are removed from the result (the export
    has no ids).  Children whose parent is missing stay at the top level.
    """
    ordered = sorted(flat_steps, key=_sort_value)
    repeats_by_id = {
        s.get('id'): s for s in ordered if s.get('step_type') == REPEAT_STEP_TYPE and s.get('id')
    }
    children: Dict[Any, List[Dict[str, Any]]] = {}
    top_level: List[Dict[str, Any]] = []
    for step in ordered:
        parent_id = step.get('parent_step_id')
        if parent_id and parent_id in repeats_by_id:
            children.setdefault(parent_id, []).append(step)
        else:
            top_level.append(step)

    def _clean(step: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in step.items() if k not in ('id', 'parent_step_id')}

    result: List[Dict[str, Any]] = []
    for step in top_level:
        exported = _clean(step)
        if step.get('step_type') == REPEAT_STEP_TYPE:
            exported['steps'] = [_clean(c) for c in children.get(step.get('id'), [])]
        result.append(exported)
    return result


class StepTreeError(ValueError):
    """The imported step list has an invalid nesting shape."""


def flatten_imported_steps(steps: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Optional[int]]]:
    """Import shape → ``[(step, parent_index)]`` in final ``sort`` order.

    Accepts the nested shape (``steps`` under a repeat) and the flat shape
    (steps carrying ``id`` + ``parent_step_id``).  ``parent_index`` is the
    index of the parent repeat in the returned list (``None`` for
    top-level steps).  Nested ``steps`` live in array order; a child's own
    ``sort`` is ignored.  Raises ``StepTreeError`` on: ``steps`` under a
    non-repeat, a repeat inside a repeat, a flat ``parent_step_id`` that
    does not resolve to a repeat.
    """
    flat: List[Tuple[Dict[str, Any], Optional[int]]] = []
    index_by_old_id: Dict[Any, int] = {}
    for position, step in enumerate(steps):
        if not isinstance(step, dict):
            raise StepTreeError(f'steps[{position}] must be an object')
        nested = step.get('steps')
        is_repeat = step.get('step_type') == REPEAT_STEP_TYPE
        if nested and not is_repeat:
            raise StepTreeError(f'steps[{position}]: only repeat steps may contain nested steps')
        parent_index = len(flat)
        flat.append(({k: v for k, v in step.items() if k != 'steps'}, None))
        if step.get('id') is not None:
            index_by_old_id[step['id']] = parent_index
        for child_position, child in enumerate(nested or []):
            if not isinstance(child, dict):
                raise StepTreeError(f'steps[{position}].steps[{child_position}] must be an object')
            if child.get('step_type') == REPEAT_STEP_TYPE or child.get('steps'):
                raise StepTreeError(
                    f'steps[{position}].steps[{child_position}]: repeat steps support one level of nesting only'
                )
            flat.append(({k: v for k, v in child.items() if k != 'steps'}, parent_index))

    # Flat shape: resolve parent_step_id against the old ids.
    resolved: List[Tuple[Dict[str, Any], Optional[int]]] = []
    for position, (step, parent_index) in enumerate(flat):
        old_parent = step.get('parent_step_id')
        if parent_index is None and old_parent:
            if old_parent not in index_by_old_id:
                raise StepTreeError(f'steps[{position}]: parent_step_id "{old_parent}" does not exist in the import')
            parent_index = index_by_old_id[old_parent]
            parent_step = flat[parent_index][0]
            if parent_step.get('step_type') != REPEAT_STEP_TYPE:
                raise StepTreeError(f'steps[{position}]: parent_step_id "{old_parent}" is not a repeat step')
            if parent_step.get('parent_step_id') or step.get('step_type') == REPEAT_STEP_TYPE:
                raise StepTreeError(f'steps[{position}]: repeat steps support one level of nesting only')
        resolved.append((step, parent_index))
    return resolved
