"""Turn a template into use-case steps — the one expansion implementation.

``import_template`` (insert into an existing use case) and ``import_usecase``
(expand ``template`` placeholder steps of an export JSON) both go through
here, so inserted steps always carry the same linkage
(``template_id`` / ``template_step_id`` / ``template_version``) and the same
field copy (``step_copy.copy_step_fields``).

Positioning is ordinal: ``splice_and_renumber`` places the new block by
*index* into the sorted existing steps and renumbers everything ``1..n``,
so gaps in historical ``sort`` values disappear instead of being compared
numerically.
"""
import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from boto3.dynamodb.conditions import Key
from pydantic import BaseModel, Field

from secret_steps import secret_keys_of_steps
from step_copy import copy_step_fields
from template_store import get_template_metadata

#: ``step_type`` of a placeholder step in an export JSON.  Not an executable
#: step: ``/import`` replaces it with the template's steps.
TEMPLATE_STEP_TYPE = 'template'

#: The only fields a placeholder may carry.
PLACEHOLDER_FIELDS = frozenset({'sort', 'step_type', 'template_id'})

#: Templates cannot contain placeholders (no nesting).
NESTED_TEMPLATE_ERROR = 'templates cannot contain template steps'

_UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def is_placeholder(step: Any) -> bool:
    return isinstance(step, dict) and step.get('step_type') == TEMPLATE_STEP_TYPE


def placeholder_error(steps: List[Any]) -> Optional[str]:
    """Validate the placeholders of an import ``steps`` list; ``None`` when fine.

    A placeholder must have exactly ``sort``, ``step_type`` and a UUID
    ``template_id``, and may only appear at the top level (never under a
    repeat).
    """
    for position, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        for child_position, child in enumerate(step.get('steps') or []):
            if is_placeholder(child):
                return f'steps[{position}].steps[{child_position}]: template steps are only allowed at the top level'
        if not is_placeholder(step):
            continue
        extra = sorted(set(step) - PLACEHOLDER_FIELDS)
        if extra:
            return f'steps[{position}]: template steps may only have sort, step_type and template_id (got {", ".join(extra)})'
        template_id = step.get('template_id')
        if not isinstance(template_id, str) or not _UUID_RE.match(template_id):
            return f'steps[{position}]: template_id must be a template UUID'
    return None


def placeholder_template_ids(steps: List[Any]) -> List[str]:
    """Distinct ``template_id`` values of the top-level placeholders, in file order."""
    ids: List[str] = []
    for step in steps:
        if is_placeholder(step) and step.get('template_id') not in ids:
            ids.append(step['template_id'])
    return ids


class TemplateBundle(BaseModel):
    """Everything needed to expand one template: metadata, ordered steps, variables."""

    metadata: Dict[str, Any]
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    variables: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def template_id(self) -> str:
        return str(self.metadata.get('id', ''))

    @property
    def version(self) -> int:
        return int(self.metadata.get('version', 1))


def load_template_bundle(table, template_id: str) -> Optional[TemplateBundle]:
    """Load metadata, steps (query, sorted by ``sort``) and variables.

    Returns ``None`` when the template metadata record does not exist.
    """
    metadata = get_template_metadata(table, template_id)
    if metadata is None:
        return None

    steps = table.query(
        KeyConditionExpression=Key('pk').eq(f'TEMPLATE#{template_id}') & Key('sk').begins_with('STEP#')
    ).get('Items', [])
    steps.sort(key=lambda s: int(s.get('sort', 0)))

    variables_item = table.get_item(Key={'pk': f'TEMPLATE#{template_id}', 'sk': 'VARIABLES'}).get('Item') or {}
    return TemplateBundle(metadata=metadata, steps=steps, variables=list(variables_item.get('variables', []) or []))


def build_linked_steps(bundle: TemplateBundle, usecase_id: str, first_sort: int, now: str) -> List[Dict[str, Any]]:
    """New ``STEP#`` items for ``usecase_id`` copied from the bundle's steps.

    Fresh ids, consecutive ``sort`` from ``first_sort``, the copyable
    definition fields, and the template linkage used by the
    "update from template" flow.
    """
    linked: List[Dict[str, Any]] = []
    for offset, template_step in enumerate(bundle.steps):
        step_id = str(uuid4())
        linked.append({
            'pk': f'USECASE#{usecase_id}',
            'sk': f'STEP#{step_id}',
            'id': step_id,
            'sort': first_sort + offset,
            'created_at': now,
            'template_id': bundle.template_id,
            'template_step_id': template_step.get('id', ''),
            'template_version': bundle.version,
            **copy_step_fields(template_step),
        })
    return linked


def merge_variables(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """``existing`` first and unchanged; ``incoming`` keys not yet present appended in order."""
    merged = list(existing)
    seen = {v.get('key') for v in existing}
    for variable in incoming:
        if variable.get('key') in seen:
            continue
        seen.add(variable.get('key'))
        merged.append(variable)
    return merged


def template_secret_keys(bundle: TemplateBundle) -> List[str]:
    """Distinct ``secret_key`` values of the template's ``secret`` steps, in step order."""
    return secret_keys_of_steps(bundle.steps)


def splice_and_renumber(existing_sorted: List[Dict[str, Any]], new_steps: List[Dict[str, Any]],
                        position: int) -> List[Dict[str, Any]]:
    """Insert ``new_steps`` so the first one becomes step ``position``; renumber ``1..n``.

    ``existing_sorted`` must already be in ``sort`` order.  ``sort`` is
    assigned in place on every step; the returned list holds the *existing*
    steps whose ``sort`` changed (the caller writes those plus every new
    step).  ``position`` must be within ``1..len(existing)+1``.
    """
    if not 1 <= position <= len(existing_sorted) + 1:
        raise ValueError(f'insert_position must be between 1 and {len(existing_sorted) + 1}')

    ordered = existing_sorted[:position - 1] + new_steps + existing_sorted[position - 1:]
    changed: List[Dict[str, Any]] = []
    new_ids = {id(step) for step in new_steps}
    for index, step in enumerate(ordered, start=1):
        if id(step) in new_ids:
            step['sort'] = index
            continue
        if int(step.get('sort', 0)) != index:
            step['sort'] = index
            changed.append(step)
    return changed
