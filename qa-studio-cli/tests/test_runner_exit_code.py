"""Tests for ``runner.main.determine_exit_code``."""

import sys
from types import ModuleType

try:  # pragma: no cover - environment dependent
    import nova_act  # noqa: F401
    import tenacity  # noqa: F401
except ImportError:  # pragma: no cover - environment dependent
    sys.modules.setdefault("nova_act", ModuleType("nova_act"))
    sys.modules.setdefault("tenacity", ModuleType("tenacity"))

from qa_studio_cli.runner.main import determine_exit_code  # noqa: E402


class TestDetermineExitCode:
    def test_no_results_is_runner_error(self):
        assert determine_exit_code([]) == 2

    def test_all_success(self):
        assert determine_exit_code([{"status": "success"}, {"status": "success"}]) == 0

    def test_any_failed(self):
        assert determine_exit_code([{"status": "success"}, {"status": "failed"}]) == 1

    def test_skipped_is_non_zero(self):
        assert determine_exit_code([{"status": "success"}, {"status": "skipped"}]) == 1
