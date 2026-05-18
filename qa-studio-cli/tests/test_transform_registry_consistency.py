"""Cross-package consistency check: worker and CLI transform registries.

The transform framework is duplicated between
``web-app/worker/transform/`` and
``qa-studio-cli/qa_studio_cli/runner/transform/`` because the worker
runs in Fargate and the CLI runs locally. The two implementations MUST
expose the same set of operation names.

This test imports the worker package by walking up the filesystem to
find the monorepo root. When the worker source is not present (e.g. the
CLI is installed standalone), the test is skipped with a clear message.

If you add or remove an operation, update both sides.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

from qa_studio_cli.runner.transform.base import (
    TRANSFORM_OPERATIONS as CLI_OPERATIONS,
)


def _find_worker_package() -> Path | None:
    """Walk up from this test file to find ``web-app/worker/transform``.

    Returns the directory to put on ``sys.path`` so ``import transform``
    resolves the worker copy, or None if not found in the monorepo.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        worker_dir = parent / "web-app" / "worker"
        if (worker_dir / "transform" / "__init__.py").exists():
            return worker_dir
    return None


def _load_worker_transform() -> ModuleType | None:
    """Load the worker's ``transform`` package without polluting sys.modules.

    The worker's package is named ``transform`` (no qualified prefix), so we
    have to insert the worker directory onto ``sys.path`` and import. We
    snapshot the worker's registry into a dict and tear down the import
    immediately afterwards so other CLI tests aren't affected.
    """
    worker_dir = _find_worker_package()
    if worker_dir is None:
        return None

    sys.path.insert(0, str(worker_dir))
    # Drop any previously cached `transform` modules to avoid colliding
    # with the CLI's transform import order; the CLI uses the fully
    # qualified name ``qa_studio_cli.runner.transform``, so they live in
    # different sys.modules keys, but the worker uses bare ``transform``.
    keys_to_clear = [k for k in sys.modules if k == "transform" or k.startswith("transform.")]
    saved = {k: sys.modules.pop(k) for k in keys_to_clear}
    try:
        return importlib.import_module("transform")
    finally:
        sys.path.pop(0)
        # Restore anything we displaced.
        for k, v in saved.items():
            sys.modules.setdefault(k, v)


@pytest.fixture(scope="module")
def worker_operation_names() -> set[str]:
    module = _load_worker_transform()
    if module is None:
        pytest.skip("Worker source not present alongside CLI; skipping cross-package check.")
    return set(module.TRANSFORM_OPERATIONS.keys())


def test_registries_have_identical_operation_sets(worker_operation_names):
    cli_names = set(CLI_OPERATIONS.keys())
    missing_in_cli = worker_operation_names - cli_names
    missing_in_worker = cli_names - worker_operation_names
    assert not missing_in_cli and not missing_in_worker, (
        f"Transform registries diverged. "
        f"In worker but not CLI: {sorted(missing_in_cli) or 'none'}. "
        f"In CLI but not worker: {sorted(missing_in_worker) or 'none'}. "
        f"Update both sides when adding or removing an operation."
    )


def test_args_models_have_same_field_names(worker_operation_names):
    """Per-op argument shape consistency.

    We don't compare full schemas (pydantic field types may render
    differently across versions), but the set of field names must match.
    """
    module = _load_worker_transform()
    if module is None:
        pytest.skip("Worker source not present alongside CLI.")
    worker_ops = module.TRANSFORM_OPERATIONS

    mismatches = []
    for name in worker_operation_names & set(CLI_OPERATIONS.keys()):
        worker_fields = set(worker_ops[name].args_model.model_fields.keys())
        cli_fields = set(CLI_OPERATIONS[name].args_model.model_fields.keys())
        if worker_fields != cli_fields:
            mismatches.append((name, worker_fields, cli_fields))

    assert not mismatches, (
        "Operation arg-model field sets diverged between worker and CLI: "
        + "; ".join(
            f"{name}: worker={sorted(w)} cli={sorted(c)}"
            for name, w, c in mismatches
        )
    )


def _load_worker_date_compare():
    """Load the worker's transform.date_compare module the same way."""
    worker_dir = _find_worker_package()
    if worker_dir is None:
        return None
    sys.path.insert(0, str(worker_dir))
    keys_to_clear = [k for k in sys.modules if k == "transform" or k.startswith("transform.")]
    saved = {k: sys.modules.pop(k) for k in keys_to_clear}
    try:
        return importlib.import_module("transform.date_compare")
    finally:
        sys.path.pop(0)
        for k, v in saved.items():
            sys.modules.setdefault(k, v)


def test_date_operator_sets_match():
    """Worker and CLI must agree on the set of date operators."""
    worker_dc = _load_worker_date_compare()
    if worker_dc is None:
        pytest.skip("Worker source not present alongside CLI.")
    from qa_studio_cli.runner.transform.date_compare import DATE_OPERATORS as CLI_DATE_OPERATORS
    assert set(worker_dc.DATE_OPERATORS) == set(CLI_DATE_OPERATORS), (
        f"Date operator sets diverged. "
        f"worker={sorted(worker_dc.DATE_OPERATORS)}, "
        f"cli={sorted(CLI_DATE_OPERATORS)}. Update both sides."
    )


def test_naive_mixed_warning_strings_match():
    """The warning shown to users must be identical between worker and CLI."""
    worker_dc = _load_worker_date_compare()
    if worker_dc is None:
        pytest.skip("Worker source not present alongside CLI.")
    from qa_studio_cli.runner.transform.date_compare import (
        NAIVE_MIXED_WARNING as CLI_WARNING,
    )
    assert worker_dc.NAIVE_MIXED_WARNING == CLI_WARNING


def test_equals_within_payload_field_shapes_match():
    """The EqualsWithinPayload pydantic model fields must agree across packages."""
    worker_dc = _load_worker_date_compare()
    if worker_dc is None:
        pytest.skip("Worker source not present alongside CLI.")
    from qa_studio_cli.runner.transform.date_compare import EqualsWithinPayload as CLIPayload
    worker_fields = set(worker_dc.EqualsWithinPayload.model_fields.keys())
    cli_fields = set(CLIPayload.model_fields.keys())
    assert worker_fields == cli_fields, (
        f"EqualsWithinPayload fields diverged: "
        f"worker={sorted(worker_fields)}, cli={sorted(cli_fields)}"
    )
