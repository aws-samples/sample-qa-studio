"""Resolve ``dataset_id`` references on repeat steps into inline rows.

A repeat step either carries inline ``repeat_columns`` / ``repeat_rows`` or
names an application dataset (``APPLICATION#{app} / DATASET#{id}``, see
``dataset_models``) through ``dataset_id``.  ``repeat_expansion`` only
understands the inline form, so execution creation runs
``resolve_dataset_refs`` first: every referencing step gets the dataset's
``columns`` / ``rows`` copied onto it (``dataset_id`` stays), everything else
passes through untouched.  ``--dataset-file`` overrides are applied *after*
this by ``expand_repeat_steps`` (by label), so the CLI layer wins over the
application dataset.

Precedence (lowest → highest): application dataset → inline rows (a step has
one or the other) → ``--dataset-file`` / ``repeat_datasets`` override.

``resolve_dataset_refs`` is pure given the fetcher and is mirrored by the
CLI local-only path (``qa_studio_cli/runner/dataset_ref.py``); both are
driven by ``fixtures/dataset_ref_cases.json`` — change the fixture first.
``application_dataset_fetcher`` is the server-side fetcher (low-level
DynamoDB client, one memoised ``get_item`` per distinct dataset id).

Imports ``dataset_models`` (pydantic): the execute Lambdas reach this module
after ``resource_auth`` has imported ``lambda_init``.
"""
from typing import Any, Callable, Dict, List, Optional

from dataset_models import dataset_sk
from repeat_validation import REPEAT_STEP_TYPE, has_dataset_reference
from variable_merge import ItemReader

#: ``fetch(dataset_id)`` → the dataset record (``{columns, rows, ...}``) or ``None``.
DatasetFetcher = Callable[[str], Optional[Dict[str, Any]]]

#: 400 ``error`` when a referenced dataset does not exist in the use case's application.
UNRESOLVED_DATASET_ERROR = 'dataset not found'


class DatasetNotFoundError(ValueError):
    """A repeat step references a dataset the fetcher could not find."""

    def __init__(self, dataset_id: str):
        super().__init__(f'{UNRESOLVED_DATASET_ERROR}: {dataset_id}')
        self.dataset_id = dataset_id


def resolve_dataset_refs(steps: List[Dict[str, Any]], fetch_dataset: DatasetFetcher) -> List[Dict[str, Any]]:
    """New step dicts with every repeat's ``dataset_id`` resolved into ``repeat_columns`` / ``repeat_rows``.

    Each distinct ``dataset_id`` is fetched once, in first-seen step order.
    Steps without a reference are copied as they are; the fetcher is never
    called for them.  Raises ``DatasetNotFoundError`` when the fetcher
    returns ``None``.  The dataset table itself is validated later by
    ``expand_repeat_steps`` (same rules as inline rows).
    """
    datasets: Dict[str, Dict[str, Any]] = {}
    resolved: List[Dict[str, Any]] = []
    for step in steps:
        new_step = dict(step)
        if step.get('step_type') == REPEAT_STEP_TYPE and has_dataset_reference(step):
            dataset_id = step['dataset_id']
            if dataset_id not in datasets:
                dataset = fetch_dataset(dataset_id)
                if dataset is None:
                    raise DatasetNotFoundError(dataset_id)
                datasets[dataset_id] = dataset
            dataset = datasets[dataset_id]
            new_step['repeat_columns'] = list(dataset.get('columns') or [])
            new_step['repeat_rows'] = [list(row) for row in (dataset.get('rows') or [])]
        resolved.append(new_step)
    return resolved


def application_dataset_fetcher(read_item: ItemReader, application_id: Optional[str]) -> DatasetFetcher:
    """``DatasetFetcher`` bound to one application (``read_item`` from ``variable_merge``).

    Reads ``APPLICATION#{application_id} / DATASET#{dataset_id}`` once per
    distinct id and memoises the answer (including "absent"), so a caller
    that builds the execution steps twice (dry run, then the real record)
    still issues one ``get_item`` per dataset.  A use case without an
    application cannot resolve anything: every lookup is ``None`` and the
    table is never read.
    """
    cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def fetch(dataset_id: str) -> Optional[Dict[str, Any]]:
        if not application_id:
            return None
        if dataset_id not in cache:
            cache[dataset_id] = read_item(f'APPLICATION#{application_id}', dataset_sk(dataset_id))
        return cache[dataset_id]

    return fetch
