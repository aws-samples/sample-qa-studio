"""Tests for the network_assertion worker step executor."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import pytest

_WORKER_DIR = Path(__file__).resolve().parent.parent
if str(_WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKER_DIR))

from models import ExecutionStep  # noqa: E402
from network_assertion_step import execute_network_assertion_step  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _step(**overrides) -> ExecutionStep:
    defaults = dict(
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
    defaults.update(overrides)
    return ExecutionStep(**defaults)


class _FakeResponseContext:
    """Stand-in for Playwright's ``page.expect_response`` context manager."""

    def __init__(self, response):
        self.value = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _TimeoutResponseContext:
    """Stand-in that raises a Playwright-like TimeoutError on exit."""

    class TimeoutError(Exception):  # noqa: N818 — mirrors Playwright naming
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        raise _TimeoutResponseContext.TimeoutError("timeout waiting for response")


def _make_nova(
    *,
    response=None,
    timeout=False,
    act_raises=None,
):
    """Build a mock NovaAct whose page supports route / expect_response."""
    nova = MagicMock()
    page = MagicMock()
    nova.page = page

    if timeout:
        page.expect_response.return_value = _TimeoutResponseContext()
    else:
        page.expect_response.return_value = _FakeResponseContext(response)

    if act_raises is not None:
        nova.act.side_effect = act_raises
    else:
        act_result = SimpleNamespace()
        act_result.metadata = SimpleNamespace(act_id="act_1")
        nova.act.return_value = act_result

    return nova


def _make_response(
    method: str = "POST",
    url: str = "https://x.test/api/users",
    post_data=None,
    *,
    status: int = 200,
    body: Optional[bytes] = None,
    body_raises: Optional[Exception] = None,
):
    request = SimpleNamespace()
    request.method = method
    request.url = url
    request.post_data = post_data
    response = SimpleNamespace()
    response.request = request
    response.status = status

    if body_raises is not None:
        def _raise():
            raise body_raises
        response.body = _raise
    elif body is not None:
        response.body = lambda: body
    else:
        response.body = lambda: None

    return response


# ---------------------------------------------------------------------------
# Validation short-circuits
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_url_pattern(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_url_pattern=None)

        result, success, logs, actual_value = execute_network_assertion_step(nova, step)

        assert success is False
        assert "network_url_pattern" in logs
        nova.act.assert_not_called()
        nova.page.route.assert_not_called()

    def test_invalid_method(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_method="WHATEVER")

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "invalid network_method" in logs

    def test_invalid_match_type(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_request_body='{"a":1}', network_body_match_type="fuzzy")

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "network_body_match_type" in logs

    def test_oversize_request_body_rejected(self):
        nova = _make_nova(response=_make_response())
        oversize = '"' + ("a" * (1_048_577)) + '"'
        step = _step(network_request_body=oversize)

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "exceeds maximum" in logs
        nova.act.assert_not_called()

    def test_invalid_mock_json(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_mock_response="not json")

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "not valid JSON" in logs


# ---------------------------------------------------------------------------
# Assert-only mode
# ---------------------------------------------------------------------------


class TestAssertOnly:
    def test_success_no_checks(self):
        nova = _make_nova(response=_make_response())
        step = _step()

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True
        assert logs == ""
        assert "captured" in actual
        nova.page.route.assert_not_called()
        nova.page.unroute.assert_not_called()

    def test_method_match(self):
        nova = _make_nova(response=_make_response(method="POST"))
        step = _step(network_method="POST")

        _, success, _, actual = execute_network_assertion_step(nova, step)

        assert success is True
        assert "method=POST" in actual

    def test_method_mismatch(self):
        nova = _make_nova(response=_make_response(method="GET"))
        step = _step(network_method="POST")

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is False
        assert "method mismatch" in logs
        assert "fail" in actual

    def test_body_exact_match(self):
        captured = json.dumps({"name": "John"})
        nova = _make_nova(response=_make_response(post_data=captured))
        step = _step(
            network_request_body='{"name": "John"}',
            network_body_match_type="exact",
        )

        _, success, _, actual = execute_network_assertion_step(nova, step)

        assert success is True
        assert "body_match=exact:pass" in actual

    def test_body_subset_match(self):
        captured = json.dumps({"name": "John", "age": 30, "id": "abc"})
        nova = _make_nova(response=_make_response(post_data=captured))
        step = _step(
            network_request_body='{"name": "John"}',
            network_body_match_type="subset",
        )

        _, success, _, actual = execute_network_assertion_step(nova, step)

        assert success is True
        assert "body_match=subset:pass" in actual

    def test_body_mismatch(self):
        captured = json.dumps({"name": "Jane"})
        nova = _make_nova(response=_make_response(post_data=captured))
        step = _step(
            network_request_body='{"name": "John"}',
            network_body_match_type="exact",
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is False
        assert "body mismatch" in logs
        assert "fail" in actual

    def test_body_missing_on_request(self):
        nova = _make_nova(response=_make_response(post_data=None))
        step = _step(network_request_body='{"a": 1}')

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "no body" in logs


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------


class TestMocking:
    def test_static_mock_registers_route_and_cleans_up(self):
        nova = _make_nova(response=_make_response())
        mock_cfg = {"status": 201, "body": {"id": "abc"}}
        step = _step(network_mock_response=json.dumps(mock_cfg))

        _, success, _, _ = execute_network_assertion_step(nova, step)

        assert success is True
        nova.page.route.assert_called_once()
        args, _ = nova.page.route.call_args
        assert args[0] == "**/api/users"
        nova.page.unroute.assert_called_once_with("**/api/users")

    def test_static_mock_handler_fulfills_with_configured_values(self):
        nova = _make_nova(response=_make_response())
        mock_cfg = {"status": 418, "body": {"teapot": True}, "headers": {"X-Mock": "1"}}
        step = _step(network_mock_response=json.dumps(mock_cfg))

        execute_network_assertion_step(nova, step)

        # Grab the registered handler and invoke it with a fake route to
        # verify it fulfills with the right payload.
        handler = nova.page.route.call_args.args[1]
        fake_route = MagicMock()
        handler(fake_route)

        fake_route.fulfill.assert_called_once()
        kwargs = fake_route.fulfill.call_args.kwargs
        assert kwargs["status"] == 418
        assert json.loads(kwargs["body"]) == {"teapot": True}
        assert kwargs["headers"] == {"X-Mock": "1"}

    def test_passthrough_mock_merges_real_response(self):
        nova = _make_nova(response=_make_response())
        mock_cfg = {"status": 500}  # override only the status
        step = _step(
            network_mock_response=json.dumps(mock_cfg),
            network_mock_passthrough=True,
        )

        execute_network_assertion_step(nova, step)
        handler = nova.page.route.call_args.args[1]

        real = MagicMock()
        real.status = 200
        real.headers = {"X-Real": "yes"}
        real.body.return_value = b'{"id":1}'
        fake_route = MagicMock()
        fake_route.fetch.return_value = real

        handler(fake_route)

        kwargs = fake_route.fulfill.call_args.kwargs
        assert kwargs["status"] == 500  # overridden
        assert kwargs["body"] == b'{"id":1}'  # passed through
        assert kwargs["headers"]["X-Real"] == "yes"  # passed through

    def test_mock_plus_assert_both_apply(self):
        captured = json.dumps({"name": "John"})
        nova = _make_nova(response=_make_response(post_data=captured))
        step = _step(
            network_mock_response='{"status": 201}',
            network_method="POST",
            network_request_body='{"name": "John"}',
            network_body_match_type="subset",
        )

        _, success, _, actual = execute_network_assertion_step(nova, step)

        assert success is True
        assert "method=POST" in actual
        assert "body_match=subset:pass" in actual
        nova.page.route.assert_called_once()
        nova.page.unroute.assert_called_once()


# ---------------------------------------------------------------------------
# Failure + cleanup paths
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_unroute_called_when_nova_act_raises(self):
        nova = _make_nova(
            response=_make_response(), act_raises=RuntimeError("nova blew up")
        )
        step = _step(network_mock_response='{"status": 200}')

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "nova blew up" in logs
        nova.page.unroute.assert_called_once_with("**/api/users")

    def test_unroute_called_on_timeout(self):
        nova = _make_nova(timeout=True)
        step = _step(network_mock_response='{"status": 200}')

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "no request matched" in logs
        nova.page.unroute.assert_called_once_with("**/api/users")

    def test_unroute_called_on_body_match_failure(self):
        captured = json.dumps({"name": "Jane"})
        nova = _make_nova(response=_make_response(post_data=captured))
        step = _step(
            network_mock_response='{"status": 200}',
            network_request_body='{"name": "John"}',
        )

        _, success, _, _ = execute_network_assertion_step(nova, step)

        assert success is False
        nova.page.unroute.assert_called_once_with("**/api/users")

    def test_no_route_no_unroute_in_assert_only_mode(self):
        nova = _make_nova(response=_make_response())
        step = _step()  # no mock configured

        execute_network_assertion_step(nova, step)

        nova.page.route.assert_not_called()
        nova.page.unroute.assert_not_called()


# ---------------------------------------------------------------------------
# Security: log sanitization, timeout cap
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_large_request_body_truncated_in_logs(self, caplog):
        import logging

        # 2 KB of data — must be truncated in logs to 500 chars.
        big = "x" * 2000
        captured = json.dumps({"payload": big})
        nova = _make_nova(response=_make_response(post_data=captured))
        step = _step(network_request_body='{"payload": "' + big + '"}')

        caplog.set_level(logging.INFO, logger="network_assertion_step")
        _, success, _, _ = execute_network_assertion_step(nova, step)

        assert success is True
        log_text = "\n".join(rec.message for rec in caplog.records)
        # Full body (2000 x's) must not appear.  A truncated prefix should.
        assert "x" * 2000 not in log_text
        assert "truncated" in log_text

    def test_timeout_default_when_none(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_timeout=None)
        execute_network_assertion_step(nova, step)

        kwargs = nova.page.expect_response.call_args.kwargs
        assert kwargs["timeout"] == 15_000  # 15s default

    def test_timeout_capped_at_max(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_timeout=9999)  # user tried to set 9999s
        execute_network_assertion_step(nova, step)

        kwargs = nova.page.expect_response.call_args.kwargs
        assert kwargs["timeout"] == 120_000  # capped at 120s

    def test_timeout_nonpositive_falls_back_to_default(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_timeout=0)
        execute_network_assertion_step(nova, step)

        kwargs = nova.page.expect_response.call_args.kwargs
        assert kwargs["timeout"] == 15_000


# ---------------------------------------------------------------------------
# Request-side schema mode
# ---------------------------------------------------------------------------


class TestRequestSchemaMode:
    """Request body validated as JSON Schema (Draft 2020-12)."""

    def test_request_body_schema_pass(self):
        nova = _make_nova(response=_make_response(
            post_data='{"id": "abc-123"}',
        ))
        step = _step(
            network_body_match_type="schema",
            network_request_body='{"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}',
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True, logs
        assert "body_match=schema:pass" in actual

    def test_request_body_schema_fail_missing_required(self):
        nova = _make_nova(response=_make_response(
            post_data='{"name": "no id"}',
        ))
        step = _step(
            network_body_match_type="schema",
            network_request_body='{"type": "object", "required": ["id"]}',
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is False
        assert "request body mismatch (schema)" in logs
        assert "body_match=schema:fail" in actual

    def test_request_body_schema_external_ref_rejected_before_action(self):
        """Schema validation happens as part of matching, not pre-execution
        (the matcher internally rejects external $ref).  Action runs; the
        assertion fails."""
        nova = _make_nova(response=_make_response(post_data='{"x": 1}'))
        step = _step(
            network_body_match_type="schema",
            network_request_body='{"$ref": "http://evil/s.json"}',
        )

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "external $ref" in logs


# ---------------------------------------------------------------------------
# Response-side: status
# ---------------------------------------------------------------------------


class TestResponseStatusAssertion:
    def test_status_match_pass(self):
        nova = _make_nova(response=_make_response(status=201))
        step = _step(network_response_status=201)

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True, logs
        assert "resp_status=201" in actual

    def test_status_mismatch_fails(self):
        nova = _make_nova(response=_make_response(status=500))
        step = _step(network_response_status=201)

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is False
        assert "response status mismatch" in logs
        assert "expected 201" in logs
        assert "got 500" in logs
        assert "resp_status=500:fail" in actual

    def test_status_out_of_range_rejected_pre_execution(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_response_status=99)

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "between 100 and 599" in logs
        nova.act.assert_not_called()

    def test_status_non_integer_rejected_pre_execution(self):
        nova = _make_nova(response=_make_response())
        step = _step(network_response_status="not-an-int")

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "network_response_status must be an integer" in logs


# ---------------------------------------------------------------------------
# Response-side: body (subset + schema)
# ---------------------------------------------------------------------------


class TestResponseBodyAssertion:
    def test_response_body_subset_pass(self):
        body = json.dumps({"id": "abc", "created_at": "2026-01-01", "extra": "ignored"}).encode("utf-8")
        nova = _make_nova(response=_make_response(body=body))
        step = _step(
            network_response_body_match_type="subset",
            network_response_body='{"id": "abc"}',
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True, logs
        assert "resp_body=subset:pass" in actual

    def test_response_body_subset_fail_missing_key(self):
        body = json.dumps({"name": "x"}).encode("utf-8")
        nova = _make_nova(response=_make_response(body=body))
        step = _step(
            network_response_body_match_type="subset",
            network_response_body='{"id": "abc"}',
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is False
        assert "response body mismatch (subset)" in logs
        assert "resp_body=subset:fail" in actual

    def test_response_body_schema_pass(self):
        body = json.dumps({"id": "abc", "count": 5}).encode("utf-8")
        nova = _make_nova(response=_make_response(body=body))
        step = _step(
            network_response_body_match_type="schema",
            network_response_body='{"type": "object", "required": ["id"], "properties": {"count": {"type": "integer"}}}',
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True, logs
        assert "resp_body=schema:pass" in actual

    def test_response_body_schema_fail_type(self):
        body = json.dumps({"id": "abc", "count": "not a number"}).encode("utf-8")
        nova = _make_nova(response=_make_response(body=body))
        step = _step(
            network_response_body_match_type="schema",
            network_response_body='{"type": "object", "properties": {"count": {"type": "integer"}}}',
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is False
        assert "response body mismatch (schema)" in logs
        assert "resp_body=schema:fail" in actual

    def test_response_body_default_match_type_is_subset(self):
        """Setting network_response_body without an explicit match-type
        should default to 'subset' (R14)."""
        body = json.dumps({"id": "abc", "extra": True}).encode("utf-8")
        nova = _make_nova(response=_make_response(body=body))
        step = _step(
            # No network_response_body_match_type — executor defaults to subset
            network_response_body='{"id": "abc"}',
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True, logs
        assert "resp_body=subset:pass" in actual

    def test_response_body_exact_rejected_pre_execution(self):
        """The executor rejects 'exact' on the response side — mirrors the
        validator.  Catches misconfigurations that slipped past the API."""
        nova = _make_nova(response=_make_response())
        step = _step(
            network_response_body_match_type="exact",
            network_response_body='{"id": "x"}',
        )

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "network_response_body_match_type" in logs
        assert "not permitted on the response side" in logs
        nova.act.assert_not_called()

    def test_response_body_malformed_json_fails(self):
        body = b"not json at all"
        nova = _make_nova(response=_make_response(body=body))
        step = _step(
            network_response_body_match_type="subset",
            network_response_body='{"id": "x"}',
        )

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "response body" in logs

    def test_oversize_response_body_template_rejected_pre_execution(self):
        oversize = '"' + ("a" * 1_048_577) + '"'
        nova = _make_nova(response=_make_response())
        step = _step(
            network_response_body_match_type="subset",
            network_response_body=oversize,
        )

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "exceeds maximum" in logs
        nova.act.assert_not_called()

    def test_oversize_captured_response_body_rejected_post_capture(self):
        """If the server returns a huge response, the step fails eagerly —
        even if no body assertion was configured (R14)."""
        huge = ("a" * 1_048_577).encode("utf-8")
        nova = _make_nova(response=_make_response(body=huge))
        step = _step()  # no body assertion configured

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is False
        assert "captured response body size" in logs
        assert "exceeds maximum" in logs
        assert "resp_body=cap:fail" in actual


# ---------------------------------------------------------------------------
# Combined request + response assertions
# ---------------------------------------------------------------------------


class TestCombinedAssertions:
    def test_all_assertions_pass(self):
        body = json.dumps({"id": "abc-123", "user": "John"}).encode("utf-8")
        nova = _make_nova(response=_make_response(
            method="POST", post_data='{"name": "John"}',
            status=201, body=body,
        ))
        step = _step(
            network_method="POST",
            network_body_match_type="subset",
            network_request_body='{"name": "John"}',
            network_response_status=201,
            network_response_body_match_type="schema",
            network_response_body='{"type": "object", "required": ["id"]}',
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True, logs
        assert "method=POST" in actual
        assert "body_match=subset:pass" in actual
        assert "resp_status=201" in actual
        assert "resp_body=schema:pass" in actual

    def test_summary_only_contains_segments_that_ran(self):
        """With only a response-status assertion set, the summary should
        be a minimal ``resp_status=200`` with no request-side segments."""
        nova = _make_nova(response=_make_response(status=200))
        step = _step(network_response_status=200)

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True, logs
        assert actual.strip() == "resp_status=200"
        assert "method=" not in actual
        assert "body_match=" not in actual
        assert "resp_body=" not in actual

    def test_first_failing_assertion_stops_the_chain(self):
        """Method mismatch short-circuits before body / response checks."""
        nova = _make_nova(response=_make_response(method="GET"))
        step = _step(
            network_method="POST",
            network_request_body='{"x": 1}',
            network_response_status=200,
        )

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is False
        assert "method mismatch" in logs
        # Summary should reflect the failing segment, not later successes.
        assert "method=GET:fail" in actual


# ---------------------------------------------------------------------------
# Response capture edge cases
# ---------------------------------------------------------------------------


class TestResponseCaptureEdgeCases:
    def test_response_body_call_raises_is_tolerated(self):
        """If Playwright's response.body() raises, we fall back to ``None``
        and continue.  Step passes because no body assertion is set."""
        nova = _make_nova(response=_make_response(
            body_raises=RuntimeError("stream closed"),
        ))
        step = _step()  # no body assertion

        _, success, logs, actual = execute_network_assertion_step(nova, step)

        assert success is True, logs

    def test_response_body_missing_when_assertion_configured_fails_cleanly(self):
        """If body is None but the user configured a subset assertion, we
        fail with a precise message."""
        nova = _make_nova(response=_make_response(body=None))
        step = _step(
            network_response_body_match_type="subset",
            network_response_body='{"id": "x"}',
        )

        _, success, logs, _ = execute_network_assertion_step(nova, step)

        assert success is False
        assert "captured response had no body" in logs
