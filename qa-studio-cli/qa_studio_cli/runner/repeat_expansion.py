"""Unroll ``repeat`` steps for local-only runs.

Behavioural mirror of ``web-app/lambdas/endpoints/repeat_expansion.py``
(R-PARITY): in remote mode the API hands the CLI already-expanded
execution steps; in ``--local-only`` mode the CLI reads step *definitions*
and must unroll them itself.  Both modules are driven by the shared fixture
``web-app/lambdas/endpoints/fixtures/repeat_expansion_cases.json``
(``tests/test_repeat_expansion_parity.py``).  Change the fixture first,
then both modules.

Stdlib only — this runs on developer machines.

Contract (plain dicts, see the Lambda module for the full description):
``expand_repeat_steps(steps, dataset_overrides=None)`` returns the flat
list with each repeat child emitted once per row carrying
``repeat_step_id``, ``repeat_label``, ``repeat_row_index``,
``repeat_row_total`` and ``row_variables``; the repeat step itself emits
nothing; trajectory/cache fields and ``parent_step_id`` are dropped from
children; ``sort`` is renumbered 1..n.  Raises ``RepeatExpansionError``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from qa_studio_cli.validation import validate_repeat_dataset

REPEAT_STEP_TYPE = "repeat"

#: Fields never copied onto an expanded child.
_STRIPPED_FIELDS = (
    "parent_step_id",
    "trajectory_s3_key",
    "trajectory_last_updated",
    "cached_steps",
    "cache_last_updated",
)


class RepeatExpansionError(ValueError):
    """A repeat step (or a dataset override) cannot be unrolled."""


def _sort_key(step: Dict[str, Any]) -> int:
    try:
        return int(step.get("sort", 0))
    except (TypeError, ValueError):
        return 0


def _resolve_rows(
    repeat: Dict[str, Any],
    dataset_overrides: Dict[str, Dict[str, Any]],
) -> List[List[str]]:
    """Rows for ``repeat`` — the override by label when present, else stored."""
    label = repeat.get("instruction", "")
    columns = repeat.get("repeat_columns")
    rows = repeat.get("repeat_rows")
    if label in dataset_overrides:
        override = dataset_overrides[label] or {}
        override_columns = override.get("columns")
        override_rows = override.get("rows")
        errors = validate_repeat_dataset(override_columns, override_rows)
        if errors:
            raise RepeatExpansionError(
                f'dataset override for repeat "{label}" is invalid: ' + "; ".join(errors)
            )
        if sorted(override_columns) != sorted(columns or []):
            raise RepeatExpansionError(
                f'dataset override for repeat "{label}": columns '
                f"[{', '.join(override_columns)}] do not match the repeat's columns "
                f"[{', '.join(columns or [])}]"
            )
        index_of = {name: i for i, name in enumerate(override_columns)}
        return [[row[index_of[name]] for name in columns] for row in override_rows]

    errors = validate_repeat_dataset(columns, rows)
    if isinstance(rows, list) and len(rows) == 0:
        raise RepeatExpansionError(f'repeat "{label}" has no rows')
    if errors:
        raise RepeatExpansionError(f'repeat "{label}" has an invalid dataset: ' + "; ".join(errors))
    return rows


def expand_repeat_steps(
    steps: List[Dict[str, Any]],
    dataset_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Return the flat, execution-ready step list for ``steps``."""
    overrides = dict(dataset_overrides or {})
    by_id = {step.get("id"): step for step in steps if step.get("id") is not None}
    labels = {
        step.get("instruction", "")
        for step in steps
        if step.get("step_type") == REPEAT_STEP_TYPE
    }
    for label in overrides:
        if label not in labels:
            raise RepeatExpansionError(f'no repeat step with label "{label}" in this usecase')

    children_by_parent: Dict[Any, List[Dict[str, Any]]] = {}
    top_level: List[Dict[str, Any]] = []
    for step in steps:
        parent_id = step.get("parent_step_id")
        if not parent_id:
            top_level.append(step)
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            raise RepeatExpansionError(f'parent_step_id "{parent_id}" does not exist in this usecase')
        if parent.get("step_type") != REPEAT_STEP_TYPE:
            raise RepeatExpansionError(f'parent_step_id "{parent_id}" is not a repeat step')
        if parent.get("parent_step_id") or step.get("step_type") == REPEAT_STEP_TYPE:
            raise RepeatExpansionError("repeat steps support one level of nesting only")
        children_by_parent.setdefault(parent_id, []).append(step)

    result: List[Dict[str, Any]] = []
    for step in sorted(top_level, key=_sort_key):
        if step.get("step_type") != REPEAT_STEP_TYPE:
            result.append(dict(step))
            continue

        label = step.get("instruction", "")
        children = sorted(children_by_parent.get(step.get("id"), []), key=_sort_key)
        if not children:
            raise RepeatExpansionError(f'repeat "{label}" has no steps inside')
        rows = _resolve_rows(step, overrides)
        columns = step.get("repeat_columns") or []
        total = len(rows)
        for row_index, row in enumerate(rows, start=1):
            row_variables = {name: str(cell) for name, cell in zip(columns, row)}
            row_variables["RepeatIndex"] = str(row_index)
            row_variables["RepeatTotal"] = str(total)
            for child in children:
                expanded = {k: v for k, v in child.items() if k not in _STRIPPED_FIELDS}
                expanded["repeat_step_id"] = step.get("id")
                expanded["repeat_label"] = label
                expanded["repeat_row_index"] = row_index
                expanded["repeat_row_total"] = total
                expanded["row_variables"] = dict(row_variables)
                result.append(expanded)

    for position, step in enumerate(result, start=1):
        step["sort"] = position
    return result
