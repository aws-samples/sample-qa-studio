"""Tests for the CLI StepExecutor's network_assertion dispatch and behaviour.

``step_executor`` imports ``nova_act`` at module level, which isn't
installed in the local test venv.  We stub it in sys.modules before
import so the executor class loads.  The test then drives a MagicMock
``NovaAct`` directly.
"""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# --- Stub nova_act before importing step_executor --------------------------


def _install_nova_act_stub() -> None:
    if "nova_act" in sys.modules:
        return
    mod = types.ModuleType("nova_act")
    mod.NovaAct = type("NovaAct", (), {})
    mod.BOOL_SCHEMA = {"type": "boolean"}
    sys.modules["nova_act"] = mod


_install_nova_act_stub()

from qa_studio_cli.runner.step_executor import StepExecutor  # noqa: E402


# --- Helpers ---------------------------------------------------------------


class _FakeResponseContext:
    def __init__(self, response):
        self.value = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _TimeoutResponseContext:
    class TimeoutError(Exception):  # noqa: N818
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        raise _TimeoutResponseContext.TimeoutError("timeout waiting for response")


def _make_response(
    method="POST",
    url="https://x.test/api/users",
    post_data=None,
    *,
    status=200,
    body=None,
    body_raises=None,
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


def _make_executor(response=None, timeout=False, act_raises=None) -> StepExecutor:
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
        nova.act.return_value = SimpleNamespace(metadata=SimpleNamespace(act_id="a1"))

    return StepExecutor(nova)


def _step(**overrides) -> dict:
    base = {
        "step_type": "network_assertion",
        "instruction": "Click submit",
        "network_url_pattern": "**/api/users",
    }
    base.update(overrides)
    return base


# --- Dispatch --------------------------------------------------------------


class TestDispatch:
    def test_dispatch_routes_to_network_assertion(self):
        executor = _make_executor(response=_make_response())
        executor._execute_network_assertion = MagicMock(return_value=SimpleNamespace())

        executor.execute(_step(), variables={}, runtime_variables={})
        executor._execute_network_assertion.assert_called_once()


# --- Validation short-circuits --------------------------------------------


class TestValidation:
    def test_missing_url_pattern(self):
        executor = _make_executor(response=_make_response())
        result = executor.execute(
            _step(network_url_pattern=""), variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "network_url_pattern" in result.logs
        executor.nova.act.assert_not_called()

    def test_invalid_method(self):
        executor = _make_executor(response=_make_response())
        result = executor.execute(
            _step(network_method="WHATEVER"), variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "invalid network_method" in result.logs

    def test_oversize_body_rejected(self):
        executor = _make_executor(response=_make_response())
        oversize = '"' + "a" * 1_048_577 + '"'
        result = executor.execute(
            _step(network_request_body=oversize), variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "exceeds maximum" in result.logs
        executor.nova.act.assert_not_called()

    def test_invalid_mock_json(self):
        executor = _make_executor(response=_make_response())
        result = executor.execute(
            _step(network_mock_response="not json"), variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "not valid JSON" in result.logs


# --- Assert-only mode -----------------------------------------------------


class TestAssertOnly:
    def test_happy_path(self):
        executor = _make_executor(response=_make_response())
        result = executor.execute(_step(), variables={}, runtime_variables={})
        assert result.success is True
        assert result.logs == ""
        assert "captured" in result.actual_value

    def test_method_match(self):
        executor = _make_executor(response=_make_response(method="POST"))
        result = executor.execute(
            _step(network_method="POST"), variables={}, runtime_variables={},
        )
        assert result.success is True
        assert "method=POST" in result.actual_value

    def test_method_mismatch(self):
        executor = _make_executor(response=_make_response(method="GET"))
        result = executor.execute(
            _step(network_method="POST"), variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "method mismatch" in result.logs

    def test_body_exact_match(self):
        captured = json.dumps({"name": "John"})
        executor = _make_executor(response=_make_response(post_data=captured))
        result = executor.execute(
            _step(
                network_request_body='{"name": "John"}',
                network_body_match_type="exact",
            ),
            variables={},
            runtime_variables={},
        )
        assert result.success is True
        assert "body_match=exact:pass" in result.actual_value

    def test_body_subset_match(self):
        captured = json.dumps({"name": "John", "age": 30, "id": "abc"})
        executor = _make_executor(response=_make_response(post_data=captured))
        result = executor.execute(
            _step(
                network_request_body='{"name": "John"}',
                network_body_match_type="subset",
            ),
            variables={},
            runtime_variables={},
        )
        assert result.success is True
        assert "body_match=subset:pass" in result.actual_value

    def test_body_mismatch_fails(self):
        captured = json.dumps({"name": "Jane"})
        executor = _make_executor(response=_make_response(post_data=captured))
        result = executor.execute(
            _step(network_request_body='{"name": "John"}'),
            variables={},
            runtime_variables={},
        )
        assert result.success is False
        assert "body mismatch" in result.logs


# --- Mocking + cleanup ----------------------------------------------------


class TestMockingAndCleanup:
    def test_static_mock_registers_and_unroutes(self):
        executor = _make_executor(response=_make_response())
        result = executor.execute(
            _step(network_mock_response='{"status": 201}'),
            variables={},
            runtime_variables={},
        )
        assert result.success is True
        executor.nova.page.route.assert_called_once()
        executor.nova.page.unroute.assert_called_once_with("**/api/users")

    def test_unroute_on_nova_act_failure(self):
        executor = _make_executor(
            response=_make_response(), act_raises=RuntimeError("boom"),
        )
        result = executor.execute(
            _step(network_mock_response='{"status": 200}'),
            variables={},
            runtime_variables={},
        )
        assert result.success is False
        assert "boom" in result.logs
        executor.nova.page.unroute.assert_called_once_with("**/api/users")

    def test_unroute_on_timeout(self):
        executor = _make_executor(timeout=True)
        result = executor.execute(
            _step(network_mock_response='{"status": 200}'),
            variables={},
            runtime_variables={},
        )
        assert result.success is False
        assert "no request matched" in result.logs
        executor.nova.page.unroute.assert_called_once_with("**/api/users")

    def test_no_mock_no_unroute(self):
        executor = _make_executor(response=_make_response())
        executor.execute(_step(), variables={}, runtime_variables={})
        executor.nova.page.route.assert_not_called()
        executor.nova.page.unroute.assert_not_called()


# --- Security: timeout cap + log sanitization -----------------------------


class TestSecurity:
    def test_timeout_default(self):
        executor = _make_executor(response=_make_response())
        executor.execute(_step(), variables={}, runtime_variables={})
        kwargs = executor.nova.page.expect_response.call_args.kwargs
        assert kwargs["timeout"] == 15_000

    def test_timeout_capped(self):
        executor = _make_executor(response=_make_response())
        executor.execute(
            _step(network_timeout=9999), variables={}, runtime_variables={},
        )
        kwargs = executor.nova.page.expect_response.call_args.kwargs
        assert kwargs["timeout"] == 120_000

    def test_timeout_nonpositive_falls_back(self):
        executor = _make_executor(response=_make_response())
        executor.execute(
            _step(network_timeout=0), variables={}, runtime_variables={},
        )
        kwargs = executor.nova.page.expect_response.call_args.kwargs
        assert kwargs["timeout"] == 15_000

    def test_large_body_truncated_in_logs(self, caplog):
        import logging

        big = "x" * 2000
        captured = json.dumps({"payload": big})
        executor = _make_executor(response=_make_response(post_data=captured))
        caplog.set_level(logging.INFO, logger="qa_studio_cli.runner.step_executor")
        executor.execute(
            _step(network_request_body='{"payload": "' + big + '"}'),
            variables={},
            runtime_variables={},
        )
        text = "\n".join(r.message for r in caplog.records)
        assert "x" * 2000 not in text
        assert "truncated" in text


# --- Request-side: schema mode --------------------------------------------


class TestRequestSchemaMode:
    def test_request_body_schema_pass(self):
        executor = _make_executor(response=_make_response(
            post_data='{"id": "abc"}',
        ))
        result = executor.execute(
            _step(
                network_body_match_type="schema",
                network_request_body='{"type": "object", "required": ["id"]}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is True, result.logs
        assert "body_match=schema:pass" in result.actual_value

    def test_request_body_schema_fail(self):
        executor = _make_executor(response=_make_response(
            post_data='{"name": "no id"}',
        ))
        result = executor.execute(
            _step(
                network_body_match_type="schema",
                network_request_body='{"type": "object", "required": ["id"]}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "request body mismatch (schema)" in result.logs
        assert "body_match=schema:fail" in result.actual_value

    def test_request_body_schema_external_ref_rejected_at_match(self):
        executor = _make_executor(response=_make_response(post_data='{"x": 1}'))
        result = executor.execute(
            _step(
                network_body_match_type="schema",
                network_request_body='{"$ref": "http://evil/s.json"}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "external $ref" in result.logs


# --- Response-side: status ------------------------------------------------


class TestResponseStatusAssertion:
    def test_status_match(self):
        executor = _make_executor(response=_make_response(status=201))
        result = executor.execute(
            _step(network_response_status=201),
            variables={}, runtime_variables={},
        )
        assert result.success is True, result.logs
        assert "resp_status=201" in result.actual_value

    def test_status_mismatch(self):
        executor = _make_executor(response=_make_response(status=500))
        result = executor.execute(
            _step(network_response_status=201),
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "response status mismatch" in result.logs
        assert "resp_status=500:fail" in result.actual_value

    def test_status_out_of_range_pre_execution(self):
        executor = _make_executor(response=_make_response())
        result = executor.execute(
            _step(network_response_status=99),
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "between 100 and 599" in result.logs
        executor.nova.act.assert_not_called()

    def test_status_non_integer_pre_execution(self):
        executor = _make_executor(response=_make_response())
        result = executor.execute(
            _step(network_response_status="nope"),
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "network_response_status must be an integer" in result.logs


# --- Response-side: body (subset + schema) --------------------------------


class TestResponseBodyAssertion:
    def test_response_body_subset_pass(self):
        body = json.dumps({"id": "abc", "extra": "ignored"}).encode("utf-8")
        executor = _make_executor(response=_make_response(body=body))
        result = executor.execute(
            _step(
                network_response_body_match_type="subset",
                network_response_body='{"id": "abc"}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is True, result.logs
        assert "resp_body=subset:pass" in result.actual_value

    def test_response_body_subset_fail(self):
        body = json.dumps({"name": "x"}).encode("utf-8")
        executor = _make_executor(response=_make_response(body=body))
        result = executor.execute(
            _step(
                network_response_body_match_type="subset",
                network_response_body='{"id": "abc"}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "response body mismatch (subset)" in result.logs
        assert "resp_body=subset:fail" in result.actual_value

    def test_response_body_schema_pass(self):
        body = json.dumps({"id": "abc"}).encode("utf-8")
        executor = _make_executor(response=_make_response(body=body))
        result = executor.execute(
            _step(
                network_response_body_match_type="schema",
                network_response_body='{"type": "object", "required": ["id"]}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is True, result.logs
        assert "resp_body=schema:pass" in result.actual_value

    def test_response_body_default_match_type_is_subset(self):
        body = json.dumps({"id": "abc"}).encode("utf-8")
        executor = _make_executor(response=_make_response(body=body))
        result = executor.execute(
            _step(
                # No explicit match type — default subset.
                network_response_body='{"id": "abc"}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is True, result.logs
        assert "resp_body=subset:pass" in result.actual_value

    def test_response_body_exact_rejected_pre_execution(self):
        executor = _make_executor(response=_make_response())
        result = executor.execute(
            _step(
                network_response_body_match_type="exact",
                network_response_body='{"id": "x"}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "network_response_body_match_type" in result.logs
        assert "not permitted on the response side" in result.logs
        executor.nova.act.assert_not_called()

    def test_oversize_captured_response_rejected(self):
        huge = ("a" * 1_048_577).encode("utf-8")
        executor = _make_executor(response=_make_response(body=huge))
        result = executor.execute(
            _step(),  # no body assertion — size check still runs
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "captured response body size" in result.logs
        assert "resp_body=cap:fail" in result.actual_value


# --- Combined --------------------------------------------------------------


class TestCombinedAssertions:
    def test_all_pass(self):
        body = json.dumps({"id": "xyz", "user": "John"}).encode("utf-8")
        executor = _make_executor(response=_make_response(
            method="POST", post_data='{"name": "John"}',
            status=201, body=body,
        ))
        result = executor.execute(
            _step(
                network_method="POST",
                network_body_match_type="subset",
                network_request_body='{"name": "John"}',
                network_response_status=201,
                network_response_body_match_type="schema",
                network_response_body='{"type": "object", "required": ["id"]}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is True, result.logs
        assert "method=POST" in result.actual_value
        assert "body_match=subset:pass" in result.actual_value
        assert "resp_status=201" in result.actual_value
        assert "resp_body=schema:pass" in result.actual_value

    def test_summary_only_includes_run_segments(self):
        executor = _make_executor(response=_make_response(status=200))
        result = executor.execute(
            _step(network_response_status=200),
            variables={}, runtime_variables={},
        )
        assert result.success is True, result.logs
        assert result.actual_value.strip() == "resp_status=200"


# --- Response body capture edge cases -------------------------------------


class TestResponseBodyEdgeCases:
    def test_response_body_call_raises_tolerated(self):
        executor = _make_executor(response=_make_response(
            body_raises=RuntimeError("stream closed"),
        ))
        result = executor.execute(
            _step(),  # no body assertion
            variables={}, runtime_variables={},
        )
        assert result.success is True, result.logs

    def test_response_body_missing_with_assertion_fails(self):
        executor = _make_executor(response=_make_response(body=None))
        result = executor.execute(
            _step(
                network_response_body_match_type="subset",
                network_response_body='{"id": "x"}',
            ),
            variables={}, runtime_variables={},
        )
        assert result.success is False
        assert "captured response had no body" in result.logs
