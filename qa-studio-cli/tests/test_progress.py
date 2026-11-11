"""Tests for ``runner.progress`` — the user-facing progress lines of ``qa-studio run``.

The line shapes are a documented contract (``docs/ci-cd-integration.md``), so
every shape is pinned here with a frozen clock.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from qa_studio_cli.runner import progress
from qa_studio_cli.utils import log_filters

FROZEN = datetime(2025, 1, 2, 14, 2, 11)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(progress, "_now", lambda: FROZEN)
    log_filters.clear_registered_secrets()
    yield
    log_filters.clear_registered_secrets()


class TestStepLabel:
    def test_plain_step(self):
        assert progress.step_label({"sort": 7}) == "Step 7"

    def test_repeat_row(self):
        step = {"sort": 7, "repeat_row_index": 2, "repeat_row_total": 3}
        assert progress.step_label(step) == "Step 7 (row 2/3)"

    def test_missing_sort_defaults_to_zero(self):
        assert progress.step_label({}) == "Step 0"

    def test_missing_total_renders_question_mark(self):
        assert progress.step_label({"sort": 1, "repeat_row_index": 1}) == "Step 1 (row 1/?)"


class TestTestStarted:
    def test_without_execution_id(self, capsys):
        progress.test_started("Login with valid credentials")
        captured = capsys.readouterr()
        assert captured.err == '[14:02:11] Executing Test "Login with valid credentials"\n'
        assert captured.out == ""

    def test_with_execution_id(self, capsys):
        progress.test_started("Checkout as guest", execution_id="0190abc")
        captured = capsys.readouterr()
        assert captured.err == '[14:02:11] Executing Test "Checkout as guest" (execution 0190abc)\n'
        assert captured.out == ""


class TestStepStarted:
    def test_plain_step(self, capsys):
        progress.step_started({"sort": 1}, "Open the login page")
        captured = capsys.readouterr()
        assert captured.err == "[14:02:11] Step 1: Open the login page\n"
        assert captured.out == ""

    def test_validation_step_appends_value(self, capsys):
        step = {"sort": 5, "validation_value": "Welcome back, Jane"}
        progress.step_started(step, "Check the greeting in the header")
        captured = capsys.readouterr()
        assert captured.err == "[14:02:11] Step 5: Check the greeting in the header (Welcome back, Jane)\n"

    def test_empty_validation_value_is_omitted(self, capsys):
        progress.step_started({"sort": 2, "validation_value": ""}, "Click Sign in")
        assert capsys.readouterr().err == "[14:02:11] Step 2: Click Sign in\n"

    def test_repeat_row_step(self, capsys):
        step = {"sort": 3, "repeat_row_index": 2, "repeat_row_total": 5}
        progress.step_started(step, "Type b@x.test")
        assert capsys.readouterr().err == "[14:02:11] Step 3 (row 2/5): Type b@x.test\n"

    def test_suite_prefix(self, capsys):
        progress.step_started({"sort": 1}, "Open the product page", test_name="Checkout as guest")
        assert capsys.readouterr().err == "[14:02:11] [Checkout as guest] Step 1: Open the product page\n"

    def test_uses_resolved_instruction_not_step_field(self, capsys):
        step = {"sort": 1, "instruction": "Type {{email}}"}
        progress.step_started(step, "Type a@x.test")
        assert capsys.readouterr().err == "[14:02:11] Step 1: Type a@x.test\n"


class TestRedaction:
    def test_registered_secret_is_masked_in_instruction(self, capsys):
        log_filters.register_secret_value("hunter2-secret")
        progress.step_started({"sort": 1}, "Type hunter2-secret into the field")
        assert capsys.readouterr().err == "[14:02:11] Step 1: Type *** into the field\n"

    def test_registered_secret_is_masked_in_validation_and_name(self, capsys):
        log_filters.register_secret_value("hunter2-secret")
        progress.step_started(
            {"sort": 1, "validation_value": "hunter2-secret"}, "Check", test_name="hunter2-secret",
        )
        assert capsys.readouterr().err == "[14:02:11] [***] Step 1: Check (***)\n"

    def test_bearer_token_pattern_is_masked_in_test_name(self, capsys):
        progress.test_started("Bearer abc.def-123")
        assert capsys.readouterr().err == '[14:02:11] Executing Test "Bearer ***"\n'


class TestContractConstants:
    """The docs quote these; a change here is a user-facing change."""

    def test_format_constants(self):
        assert progress.TEST_STARTED_FORMAT == '[{time}] Executing Test "{name}"'
        assert progress.TEST_STARTED_EXECUTION_SUFFIX == " (execution {execution_id})"
        assert progress.STEP_STARTED_FORMAT == "[{time}] {label}: {instruction}"
        assert progress.STEP_VALIDATION_SUFFIX == " ({validation_value})"
        assert progress.SUITE_PREFIX_FORMAT == "[{test_name}] "

    def test_now_is_wall_clock(self, monkeypatch):
        monkeypatch.undo()
        before = datetime.now()
        now = progress._now()
        assert isinstance(now, datetime)
        assert now >= before
