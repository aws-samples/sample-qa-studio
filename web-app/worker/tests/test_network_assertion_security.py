"""Consolidated security suite for the network_assertion step type.

These tests reassert the full security contract in one place so the
invariants are easy to review.  Each test delegates to the underlying
module under test — no logic is duplicated here.

Contract:
  1. Body size is capped at 1 MiB (UTF-8 bytes) and enforced before parsing.
  2. JSON subset matching refuses to recurse deeper than 20 levels.
  3. Route handlers are always cleaned up via ``page.unroute``.
  4. Captured request bodies are never emitted in full at INFO level.
  5. Timeouts are clamped into [default, 120] seconds — non-positive
     values fall back to the default; oversized values are capped.
  6. HTTP methods outside the Playwright-supported allow-list are
     rejected before any Nova Act action runs.
  7. Malformed mock-response JSON is rejected before any Nova Act action
     runs.
  8. URL pattern is required — the step fails fast without triggering
     Nova Act when it is missing.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_WORKER_DIR = Path(__file__).resolve().parent.parent
if str(_WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKER_DIR))

from models import ExecutionStep  # noqa: E402
from network_assertion_step import (  # noqa: E402
    MAX_BODY_SIZE,
    execute_network_assertion_step,
)
from network_matcher import MAX_DEPTH, match_subset, validate_body_size  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _step(**overrides):
    defaults = dict(
        pk="EXECUTION#e1",
        sk="EXECUTION_STEP#s1",
        step_id="s1",
        sort=1,
        instruction="Click submit",
        artefact="",
        logs=[],
        created_at="2026-04-29T00:00:00Z",
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
    defaults.update(overrides)
    return ExecutionStep(**defaults)


class _ResponseContext:
    def __init__(self, response):
        self.value = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _make_response(method="POST", url="https://x.test/api/users", body=None):
    request = SimpleNamespace(method=method, url=url, post_data=body)
    return SimpleNamespace(request=request)


def _make_nova(response=None, timeout=False, act_raises=None):
    nova = MagicMock()
    nova.page = MagicMock()
    if timeout:
        class _TO:
            def __enter__(self): return self
            def __exit__(self, *a): raise TimeoutError("playwright timeout")
        nova.page.expect_response.return_value = _TO()
    else:
        nova.page.expect_response.return_value = _ResponseContext(response or _make_response())
    if act_raises:
        nova.act.side_effect = act_raises
    else:
        nova.act.return_value = SimpleNamespace(metadata=SimpleNamespace(act_id="a1"))
    return nova


# ---------------------------------------------------------------------------
# 1. Body size cap — 1 MiB in UTF-8 bytes
# ---------------------------------------------------------------------------


class TestBodySizeCap:
    def test_at_limit_accepted(self):
        at_limit = "x" * MAX_BODY_SIZE
        ok, _ = validate_body_size(at_limit)
        assert ok is True

    def test_over_limit_rejected(self):
        over = "x" * (MAX_BODY_SIZE + 1)
        ok, err = validate_body_size(over)
        assert ok is False
        assert "exceeds maximum" in err

    def test_multibyte_measured_in_bytes(self):
        # "€" is 3 UTF-8 bytes; at_limit // 3 chars is under, +1 is over.
        at_limit_chars = MAX_BODY_SIZE // 3
        assert validate_body_size("€" * at_limit_chars)[0] is True
        assert validate_body_size("€" * (at_limit_chars + 1))[0] is False

    def test_over_limit_blocks_executor_before_nova_act(self):
        nova = _make_nova()
        oversize = '"' + "a" * (MAX_BODY_SIZE + 1) + '"'
        _, success, logs, _ = execute_network_assertion_step(
            nova, _step(network_request_body=oversize),
        )
        assert success is False
        assert "exceeds maximum" in logs
        nova.act.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Subset matcher recursion depth
# ---------------------------------------------------------------------------


class TestDepthCap:
    @staticmethod
    def _nest(depth):
        return "{}" if depth == 0 else '{"x": ' + TestDepthCap._nest(depth - 1) + "}"

    def test_at_limit_accepted(self):
        template = self._nest(MAX_DEPTH)
        ok, err = match_subset(template, json.loads(template))
        assert ok is True, err

    def test_over_limit_rejected(self):
        template = self._nest(MAX_DEPTH + 2)
        ok, err = match_subset(template, json.loads(template))
        assert ok is False
        assert "depth" in err


# ---------------------------------------------------------------------------
# 3. Route cleanup — always, even on failure paths
# ---------------------------------------------------------------------------


class TestRouteCleanup:
    def test_cleanup_on_success(self):
        nova = _make_nova()
        execute_network_assertion_step(
            nova, _step(network_mock_response='{"status":200}'),
        )
        nova.page.unroute.assert_called_once_with("**/api/users")

    def test_cleanup_on_nova_act_failure(self):
        nova = _make_nova(act_raises=RuntimeError("boom"))
        execute_network_assertion_step(
            nova, _step(network_mock_response='{"status":200}'),
        )
        nova.page.unroute.assert_called_once_with("**/api/users")

    def test_cleanup_on_timeout(self):
        nova = _make_nova(timeout=True)
        execute_network_assertion_step(
            nova, _step(network_mock_response='{"status":200}'),
        )
        nova.page.unroute.assert_called_once_with("**/api/users")

    def test_cleanup_on_body_match_failure(self):
        nova = _make_nova(response=_make_response(body='{"name":"Jane"}'))
        execute_network_assertion_step(
            nova,
            _step(
                network_mock_response='{"status":200}',
                network_request_body='{"name":"John"}',
            ),
        )
        nova.page.unroute.assert_called_once_with("**/api/users")


# ---------------------------------------------------------------------------
# 4. Log sanitization — no full body in INFO logs
# ---------------------------------------------------------------------------


class TestLogSanitization:
    def test_big_body_truncated_in_logs(self, caplog):
        big = "x" * 2000
        captured = json.dumps({"payload": big})
        nova = _make_nova(response=_make_response(body=captured))
        caplog.set_level(logging.INFO, logger="network_assertion_step")
        execute_network_assertion_step(
            nova, _step(network_request_body='{"payload": "' + big + '"}'),
        )
        text = "\n".join(r.message for r in caplog.records)
        assert "x" * 2000 not in text
        assert "truncated" in text


# ---------------------------------------------------------------------------
# 5. Timeout clamping
# ---------------------------------------------------------------------------


class TestTimeoutClamping:
    @pytest.mark.parametrize("value,expected_ms", [
        (None, 15_000),     # default
        (0, 15_000),        # non-positive → default
        (-5, 15_000),       # negative → default
        (1, 1_000),         # boundary min
        (15, 15_000),       # default explicit
        (120, 120_000),     # boundary max
        (121, 120_000),     # over max → capped
        (9999, 120_000),    # way over → capped
    ])
    def test_timeout_clamped(self, value, expected_ms):
        nova = _make_nova()
        execute_network_assertion_step(nova, _step(network_timeout=value))
        kwargs = nova.page.expect_response.call_args.kwargs
        assert kwargs["timeout"] == expected_ms


# ---------------------------------------------------------------------------
# 6. Method allow-list
# ---------------------------------------------------------------------------


class TestMethodAllowList:
    @pytest.mark.parametrize("method", [
        "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
    ])
    def test_canonical_methods_accepted(self, method):
        nova = _make_nova(response=_make_response(method=method))
        _, success, _, _ = execute_network_assertion_step(
            nova, _step(network_method=method),
        )
        assert success is True

    def test_arbitrary_method_rejected_before_action(self):
        nova = _make_nova()
        _, success, logs, _ = execute_network_assertion_step(
            nova, _step(network_method="TEAPOT"),
        )
        assert success is False
        assert "invalid network_method" in logs
        nova.act.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Malformed mock JSON
# ---------------------------------------------------------------------------


class TestMalformedMockResponse:
    def test_invalid_json_rejected(self):
        nova = _make_nova()
        _, success, logs, _ = execute_network_assertion_step(
            nova, _step(network_mock_response="not json"),
        )
        assert success is False
        assert "not valid JSON" in logs
        nova.act.assert_not_called()

    def test_non_object_rejected(self):
        nova = _make_nova()
        _, success, logs, _ = execute_network_assertion_step(
            nova, _step(network_mock_response='["not", "object"]'),
        )
        assert success is False
        assert "must be a JSON object" in logs
        nova.act.assert_not_called()


# ---------------------------------------------------------------------------
# 8. URL pattern required
# ---------------------------------------------------------------------------


class TestUrlPatternRequired:
    def test_missing_url_pattern_fails_fast(self):
        nova = _make_nova()
        _, success, logs, _ = execute_network_assertion_step(
            nova, _step(network_url_pattern=None),
        )
        assert success is False
        assert "network_url_pattern" in logs
        nova.act.assert_not_called()
        nova.page.route.assert_not_called()
