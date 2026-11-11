"""Unroll ``repeat`` steps into a flat list of execution steps.

The runner never learns what a repeat is: when an execution is created the
repeat's children are emitted once per dataset row, in row-major order,
each carrying the row's values as ``row_variables``.  This module is the
Lambda home of that logic; ``qa-studio-cli/qa_studio_cli/runner/
repeat_expansion.py`` is a behavioural mirror used by local-only runs.
Both are driven by ``fixtures/repeat_expansion_cases.json`` — change the
fixture first, then both modules.

Plain-dict contract
-------------------
``expand_repeat_steps`` operates on plain Python dicts — **not** the
DynamoDB typed attribute format.  ``execution_steps.build_execution_step_items``
deserializes STEP# records before calling it and serializes the result
again.  Numeric fields (``sort``, ``repeat_row_index``, ``repeat_row_total``)
are ints; ``row_variables`` values are always strings.

Output per expanded child
-------------------------
All original fields except ``parent_step_id``, ``trajectory_s3_key``,
``trajectory_last_updated``, ``cached_steps`` and ``cache_last_updated``
(trajectory cache is off inside a repeat), plus:

- ``repeat_step_id``    id of the repeat the step came from
- ``repeat_label``      the repeat's ``instruction``
- ``repeat_row_index``  1-based row index
- ``repeat_row_total``  row count
- ``row_variables``     ``{column: cell, "RepeatIndex": "i", "RepeatTotal": "n"}``

``sort`` is renumbered 1..n over the whole result.
"""
from typing import Any, Dict, List, Optional

from repeat_validation import REPEAT_STEP_TYPE, validate_dataset

#: Fields never copied onto an expanded child.
_STRIPPED_FIELDS = (
    'parent_step_id',
    'trajectory_s3_key',
    'trajectory_last_updated',
    'cached_steps',
    'cache_last_updated',
)


class RepeatExpansionError(ValueError):
    """A repeat step (or a dataset override) cannot be unrolled."""


def _sort_key(step: Dict[str, Any]) -> int:
    try:
        return int(step.get('sort', 0))
    except (TypeError, ValueError):
        return 0


def _resolve_rows(
    repeat: Dict[str, Any],
    dataset_overrides: Dict[str, Dict[str, Any]],
) -> List[List[str]]:
    """Rows for ``repeat`` — the override by label when present, else stored."""
    label = repeat.get('instruction', '')
    columns = repeat.get('repeat_columns')
    rows = repeat.get('repeat_rows')
    if label in dataset_overrides:
        override = dataset_overrides[label] or {}
        override_columns = override.get('columns')
        override_rows = override.get('rows')
        errors = validate_dataset(override_columns, override_rows)
        if errors:
            raise RepeatExpansionError(
                f'dataset override for repeat "{label}" is invalid: ' + '; '.join(errors)
            )
        if sorted(override_columns) != sorted(columns or []):
            raise RepeatExpansionError(
                f'dataset override for repeat "{label}": columns '
                f'[{", ".join(override_columns)}] do not match the repeat\'s columns '
                f'[{", ".join(columns or [])}]'
            )
        # Re-order cells to the stored column order so {{column}} lookups
        # are position-independent.
        index_of = {name: i for i, name in enumerate(override_columns)}
        return [[row[index_of[name]] for name in columns] for row in override_rows]

    errors = validate_dataset(columns, rows)
    if isinstance(rows, list) and len(rows) == 0:
        raise RepeatExpansionError(f'repeat "{label}" has no rows')
    if errors:
        raise RepeatExpansionError(f'repeat "{label}" has an invalid dataset: ' + '; '.join(errors))
    return rows


def expand_repeat_steps(
    steps: List[Dict[str, Any]],
    dataset_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Return the flat, execution-ready step list for ``steps``.

    Raises ``RepeatExpansionError`` for: a repeat with zero rows or zero
    children, a child whose parent is missing or not a top-level repeat, an
    override for an unknown label, override columns that differ from the
    repeat's columns, and any dataset exceeding the caps.
    """
    overrides = dict(dataset_overrides or {})
    by_id = {step.get('id'): step for step in steps if step.get('id') is not None}
    labels = {
        step.get('instruction', '')
        for step in steps
        if step.get('step_type') == REPEAT_STEP_TYPE
    }
    for label in overrides:
        if label not in labels:
            raise RepeatExpansionError(f'no repeat step with label "{label}" in this usecase')

    children_by_parent: Dict[Any, List[Dict[str, Any]]] = {}
    top_level: List[Dict[str, Any]] = []
    for step in steps:
        parent_id = step.get('parent_step_id')
        if not parent_id:
            top_level.append(step)
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            raise RepeatExpansionError(f'parent_step_id "{parent_id}" does not exist in this usecase')
        if parent.get('step_type') != REPEAT_STEP_TYPE:
            raise RepeatExpansionError(f'parent_step_id "{parent_id}" is not a repeat step')
        if parent.get('parent_step_id') or step.get('step_type') == REPEAT_STEP_TYPE:
            raise RepeatExpansionError('repeat steps support one level of nesting only')
        children_by_parent.setdefault(parent_id, []).append(step)

    result: List[Dict[str, Any]] = []
    for step in sorted(top_level, key=_sort_key):
        if step.get('step_type') != REPEAT_STEP_TYPE:
            result.append(dict(step))
            continue

        label = step.get('instruction', '')
        children = sorted(children_by_parent.get(step.get('id'), []), key=_sort_key)
        if not children:
            raise RepeatExpansionError(f'repeat "{label}" has no steps inside')
        rows = _resolve_rows(step, overrides)
        columns = step.get('repeat_columns') or []
        total = len(rows)
        for row_index, row in enumerate(rows, start=1):
            row_variables = {name: str(cell) for name, cell in zip(columns, row)}
            row_variables['RepeatIndex'] = str(row_index)
            row_variables['RepeatTotal'] = str(total)
            for child in children:
                expanded = {k: v for k, v in child.items() if k not in _STRIPPED_FIELDS}
                expanded['repeat_step_id'] = step.get('id')
                expanded['repeat_label'] = label
                expanded['repeat_row_index'] = row_index
                expanded['repeat_row_total'] = total
                expanded['row_variables'] = dict(row_variables)
                result.append(expanded)

    for position, step in enumerate(result, start=1):
        step['sort'] = position
    return result
