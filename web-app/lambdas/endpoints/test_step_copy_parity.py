"""``step_copy.COPYABLE_STEP_FIELDS`` is the single source of persisted step fields.

Two contracts are pinned here:

- The CLI's ``ExportStep`` model (``qa-studio-cli``) must declare exactly the
  same optional fields, otherwise ``qa-studio tests import`` silently drops a
  field on the client before the server ever sees it.  The CLI is a separate
  package, so the model is parsed with ``ast`` instead of imported.
- ``execution_steps.COPIED_STEP_FIELDS`` (STEP# → EXECUTION_STEP#) must cover
  every definition field except the ones that are intentionally not copied to
  an execution (repeat dataset — expanded instead; ``value_step`` — legacy).
"""
import ast
import os

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

from execution_steps import COPIED_STEP_FIELDS  # noqa: E402
from step_copy import COPYABLE_STEP_FIELDS, STEP_RUNTIME_FIELDS  # noqa: E402

_CLI_SCHEMA = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "qa-studio-cli", "qa_studio_cli", "models", "import_schema.py",
))

#: ``ExportStep`` attributes that are not per-step definition fields.
_EXPORT_STEP_NON_DEFINITION_FIELDS = {
    "sort", "instruction", "step_type",  # required
    "steps", "id", "parent_step_id",     # tree shape, remapped on import
}

#: Definition fields deliberately absent from EXECUTION_STEP# records: the
#: repeat dataset (inline or by ``dataset_id``) is resolved and expanded into
#: per-row children instead.
_NOT_COPIED_TO_EXECUTION = {"repeat_columns", "repeat_rows", "dataset_id", "value_step"}


def _export_step_annotated_fields(path: str) -> set:
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ExportStep":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError(f"class ExportStep not found in {path}")


class TestCliParity:
    @pytest.mark.skipif(
        not os.path.exists(_CLI_SCHEMA),
        reason=f"CLI checkout not present at {_CLI_SCHEMA} (lambda-only checkout)",
    )
    def test_export_step_optional_fields_equal_copyable_step_fields(self):
        cli_fields = _export_step_annotated_fields(_CLI_SCHEMA) - _EXPORT_STEP_NON_DEFINITION_FIELDS
        assert cli_fields == set(COPYABLE_STEP_FIELDS), (
            f"only in CLI: {sorted(cli_fields - set(COPYABLE_STEP_FIELDS))}; "
            f"only in lambdas: {sorted(set(COPYABLE_STEP_FIELDS) - cli_fields)}"
        )


class TestFieldLists:
    def test_no_duplicates(self):
        assert len(set(COPYABLE_STEP_FIELDS)) == len(COPYABLE_STEP_FIELDS)
        assert len(set(STEP_RUNTIME_FIELDS)) == len(STEP_RUNTIME_FIELDS)

    def test_runtime_fields_are_not_definition_fields(self):
        assert not set(STEP_RUNTIME_FIELDS) & set(COPYABLE_STEP_FIELDS)

    def test_runtime_fields(self):
        assert set(STEP_RUNTIME_FIELDS) == {
            "cached_steps", "cache_last_updated", "trajectory_s3_key", "trajectory_last_updated",
        }

    def test_execution_copy_covers_definition_and_runtime_fields(self):
        expected = (set(COPYABLE_STEP_FIELDS) - _NOT_COPIED_TO_EXECUTION) | set(STEP_RUNTIME_FIELDS)
        assert set(COPIED_STEP_FIELDS) == expected, (
            f"missing from COPIED_STEP_FIELDS: {sorted(expected - set(COPIED_STEP_FIELDS))}; "
            f"unexpected: {sorted(set(COPIED_STEP_FIELDS) - expected)}"
        )
