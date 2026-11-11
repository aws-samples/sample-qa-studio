"""Which use cases of an application reference a dataset.

Datasets are scoped to one application, so "the use cases of this app →
their repeat steps" is a bounded walk over existing records: the
association records ``APPLICATION#{app_id} / USECASE#{usecase_id}``
(written by ``handlers/associate_usecases``) and each use case's
``USECASE#{uid} / STEP#*`` partition.  No scan, no GSI, no reverse-pointer
record to keep in sync (see the design's *Alternatives considered*).

Only two write paths need the answer — ``DELETE …/datasets/{id}`` (409 body,
``find_dataset_references``) and moving a use case between applications
(``find_usecase_dataset_steps``) — so the cost per call is ``1 + len(usecases)``
queries plus one ``get_item`` per referencing use case, or one query plus one
``get_item`` per moved use case.
"""
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key

from repeat_validation import has_dataset_reference, load_usecase_steps

_USECASE_ASSOCIATION_PREFIX = 'USECASE#'


def list_application_usecase_ids(table, app_id: str) -> List[str]:
    """Use case ids associated with ``app_id`` (from the association records)."""
    response = table.query(
        KeyConditionExpression=(
            Key('pk').eq(f'APPLICATION#{app_id}') & Key('sk').begins_with(_USECASE_ASSOCIATION_PREFIX)
        )
    )
    return [
        item['sk'][len(_USECASE_ASSOCIATION_PREFIX):]
        for item in response.get('Items', [])
        if isinstance(item.get('sk'), str)
    ]


def steps_referencing_dataset(steps: List[Dict[str, Any]], dataset_id: str) -> List[Dict[str, Any]]:
    """The steps of one use case whose ``dataset_id`` is ``dataset_id``."""
    return [step for step in steps if step.get('dataset_id') == dataset_id]


def _usecase_name(table, usecase_id: str) -> str:
    item = table.get_item(Key={'pk': 'USECASES', 'sk': f'USECASE#{usecase_id}'}).get('Item') or {}
    return str(item.get('name') or usecase_id)


def find_dataset_references(table, app_id: str, dataset_id: str) -> List[Dict[str, str]]:
    """``[{usecase_id, name}]`` for every use case of ``app_id`` with a step on ``dataset_id``.

    Each use case appears once, sorted by name.  A use case whose
    ``USECASES`` record is gone is still reported, with its id as the name,
    so the caller never under-reports a reference.
    """
    references: List[Dict[str, str]] = []
    for usecase_id in list_application_usecase_ids(table, app_id):
        steps = load_usecase_steps(table, usecase_id)
        if steps_referencing_dataset(steps, dataset_id):
            references.append({'usecase_id': usecase_id, 'name': _usecase_name(table, usecase_id)})
    references.sort(key=lambda ref: (ref['name'].lower(), ref['usecase_id']))
    return references


def find_usecase_dataset_steps(table, usecase_id: str) -> Optional[Dict[str, Any]]:
    """``{usecase_id, name, steps: [{id, instruction}]}`` when any step of ``usecase_id`` references a dataset.

    Steps are in ``sort`` order.  Returns ``None`` when no step carries a
    ``dataset_id``.  Used by ``associate_usecases`` to refuse moving a use case
    whose repeat steps point at datasets of the application it is leaving.
    """
    steps = [s for s in load_usecase_steps(table, usecase_id) if has_dataset_reference(s)]
    if not steps:
        return None
    steps.sort(key=lambda s: int(s.get('sort', 0)))
    return {
        'usecase_id': usecase_id,
        'name': _usecase_name(table, usecase_id),
        'steps': [{'id': str(s.get('id', '')), 'instruction': str(s.get('instruction', ''))} for s in steps],
    }
