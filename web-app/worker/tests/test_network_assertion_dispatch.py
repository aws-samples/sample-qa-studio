"""Dispatch test for network_assertion in worker.py.

worker.py has many heavy transitive imports (nova_act, bedrock_agentcore,
etc.) that aren't installed in the local test venv.  Rather than stub the
entire dependency tree, we verify the dispatch wiring via static source
analysis plus a direct-signature check on the executor.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_WORKER_DIR = Path(__file__).resolve().parent.parent
if str(_WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKER_DIR))


class TestWorkerDispatchWiring:
    """Static checks on worker.py source + a direct executor signature check."""

    @staticmethod
    def _worker_source() -> str:
        return (_WORKER_DIR / "worker.py").read_text()

    def test_import_present(self):
        assert (
            "from network_assertion_step import execute_network_assertion_step"
            in self._worker_source()
        )

    def test_case_present_with_correct_call(self):
        source = self._worker_source()
        assert "case 'network_assertion':" in source, (
            "worker.py must have a 'network_assertion' case in its match statement"
        )
        assert "execute_network_assertion_step(nova, parsed_step)" in source, (
            "dispatch must call the executor with (nova, parsed_step) only"
        )

    def test_case_unpacks_four_tuple(self):
        """The dispatch line must destructure the 4-tuple the executor returns."""
        source = self._worker_source()
        tree = ast.parse(source)

        # Find all Assign nodes whose RHS is `execute_network_assertion_step(...)`
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "execute_network_assertion_step":
                    targets = node.targets
                    # Expect a single tuple target of length 4
                    assert len(targets) == 1
                    target = targets[0]
                    assert isinstance(target, ast.Tuple), (
                        "dispatch must unpack into a 4-tuple, got " + ast.dump(target)
                    )
                    assert len(target.elts) == 4, (
                        "dispatch must unpack 4 values (result, success, logs, actual_value)"
                    )
                    found = True
        assert found, "no assignment from execute_network_assertion_step found in worker.py"


class TestExecutorSignature:
    """The executor must be callable with (nova, step) and return 4-tuple."""

    def test_direct_call_returns_four_tuple(self):
        from models import ExecutionStep
        from network_assertion_step import execute_network_assertion_step

        step = ExecutionStep(
            pk="EXECUTION#e1",
            sk="EXECUTION_STEP#s1",
            step_id="s1",
            sort=1,
            instruction="Click submit",
            artefact="",
            logs=[],
            created_at="2026-01-01T00:00:00Z",
            secret_key="",
            step_type="network_assertion",
            validation_type="",
            validation_operator="",
            validation_value="",
            capture_variable="",
            value_type="",
            assertion_variable="",
            network_url_pattern="**/api/users",
        )

        nova = MagicMock()
        nova.page = MagicMock()

        response = SimpleNamespace()
        response.request = SimpleNamespace(
            method="POST", url="https://x.test/api/users", post_data=None,
        )

        class _Ctx:
            value = response

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        nova.page.expect_response.return_value = _Ctx()
        nova.act.return_value = SimpleNamespace(metadata=SimpleNamespace(act_id="a1"))

        out = execute_network_assertion_step(nova, step)
        assert isinstance(out, tuple) and len(out) == 4
        _, success, logs, actual_value = out
        assert success is True
        assert logs == ""
        assert isinstance(actual_value, str)
