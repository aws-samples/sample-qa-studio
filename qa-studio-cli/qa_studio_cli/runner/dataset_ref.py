"""Resolve ``dataset_id`` references on repeat steps for local-only runs.

Behavioural mirror of ``web-app/lambdas/endpoints/dataset_ref.py``: in
remote mode the server fills ``repeat_columns`` / ``repeat_rows`` from the
application dataset at execution creation; in ``--local-only`` mode the CLI
reads step *definitions* and must resolve the reference itself, fetching the
dataset through ``GET /applications/{id}/datasets/{datasetId}``
(``ApplicationsAPI.get_dataset``, needs ``api/applications.read``).  Both
modules are driven by the shared fixture ``dataset_ref_cases.json``
(server copy ``web-app/lambdas/endpoints/fixtures/``, CLI copy
``tests/fixtures/``; ``tests/test_dataset_ref.py`` asserts they are
identical).  Change the server fixture first, copy it, then both modules.

Resolution runs *before* ``resolve_repeat_datasets`` / ``expand_repeat_steps``
so a ``--dataset-file`` override still replaces the whole table by label.

Precedence (lowest → highest): application dataset → inline rows (a step has
one or the other) → ``--dataset-file`` override.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from qa_studio_cli.api.applications import READ_SCOPE, ApplicationsAPI
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.runner.repeat_expansion import REPEAT_STEP_TYPE
from qa_studio_cli.validation import has_dataset_reference

#: ``fetch(dataset_id)`` → the dataset (``{columns, rows, ...}``) or ``None`` when absent.
DatasetFetcher = Callable[[str], Optional[Dict[str, Any]]]

#: Mirrors the server's 400 ``error`` for an unresolvable reference.
UNRESOLVED_DATASET_ERROR = "dataset not found"

#: Appended to the error when the datasets route answers 403.
SCOPE_HINT = f"--local-only with application datasets needs the {READ_SCOPE} scope"


class DatasetNotFoundError(ValueError):
    """A repeat step references a dataset the fetcher could not find."""

    def __init__(self, dataset_id: str):
        super().__init__(f"{UNRESOLVED_DATASET_ERROR}: {dataset_id}")
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
        if step.get("step_type") == REPEAT_STEP_TYPE and has_dataset_reference(step):
            dataset_id = step["dataset_id"]
            if dataset_id not in datasets:
                dataset = fetch_dataset(dataset_id)
                if dataset is None:
                    raise DatasetNotFoundError(dataset_id)
                datasets[dataset_id] = dataset
            dataset = datasets[dataset_id]
            new_step["repeat_columns"] = list(dataset.get("columns") or [])
            new_step["repeat_rows"] = [list(row) for row in (dataset.get("rows") or [])]
        resolved.append(new_step)
    return resolved


def application_dataset_fetcher(applications_api: ApplicationsAPI, application_id: Optional[str]) -> DatasetFetcher:
    """``DatasetFetcher`` bound to one application, reading through the API.

    One ``GET`` per distinct id, memoised (including "absent" — a 404).  A
    use case without an application cannot resolve anything: every lookup
    is ``None`` and the API is never called.  A 403 means the token lacks
    ``api/applications.read``; it is raised as ``RuntimeError`` with the
    scope hint (exit code 2 in the runner).  Other API errors propagate.
    """
    cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def fetch(dataset_id: str) -> Optional[Dict[str, Any]]:
        if not application_id:
            return None
        if dataset_id not in cache:
            try:
                cache[dataset_id] = applications_api.get_dataset(application_id, dataset_id)
            except ApiError as e:
                if e.status_code == 404:
                    cache[dataset_id] = None
                elif e.status_code == 403:
                    raise RuntimeError(
                        f"cannot read dataset {dataset_id} of application {application_id}: "
                        f"{e.message} {SCOPE_HINT}",
                    ) from e
                else:
                    raise
        return cache[dataset_id]

    return fetch


def resolve_usecase_dataset_refs(
    steps: List[Dict[str, Any]],
    application_id: Optional[str],
    fetch_dataset: DatasetFetcher,
) -> List[Dict[str, Any]]:
    """``resolve_dataset_refs`` with the runner's error contract.

    A missing dataset becomes ``RuntimeError`` (the runner maps it to exit
    code 2): ``dataset <id> not found in application <app>``, or an explicit
    message when the use case has no application at all.
    """
    try:
        return resolve_dataset_refs(steps, fetch_dataset)
    except DatasetNotFoundError as e:
        if not application_id:
            raise RuntimeError(f"dataset {e.dataset_id} not found: the use case has no application") from e
        raise RuntimeError(f"dataset {e.dataset_id} not found in application {application_id}") from e
