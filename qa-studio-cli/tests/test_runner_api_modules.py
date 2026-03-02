"""Tests for runner API modules (usecases, executions, test_suites)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from qa_studio_cli.api.client import ApiClient
from qa_studio_cli.api.usecases import UseCaseAPI
from qa_studio_cli.api.executions import ExecutionAPI
from qa_studio_cli.api.test_suites import TestSuiteAPI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client() -> ApiClient:
    """Create an ApiClient with a mock token provider."""
    client = ApiClient(base_url="https://api.example.com", token_provider=lambda: "test-token")
    client._session = MagicMock()
    return client


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# UseCaseAPI tests
# ---------------------------------------------------------------------------

class TestUseCaseAPI:
    def setup_method(self):
        self.client = _make_client()
        self.api = UseCaseAPI(self.client)

    def test_get_usecase(self):
        self.client._session.request.return_value = _mock_response(200, {"id": "uc-1", "name": "Test"})
        result = self.api.get_usecase("uc-1")
        assert result["id"] == "uc-1"
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("GET", "https://api.example.com/api/usecase/uc-1")

    def test_get_steps(self):
        self.client._session.request.return_value = _mock_response(200, {"steps": [{"id": "s1"}]})
        result = self.api.get_steps("uc-1")
        assert result == [{"id": "s1"}]

    def test_get_variables_list_format(self):
        self.client._session.request.return_value = _mock_response(
            200, {"variables": [{"key": "url", "value": "https://example.com"}]}
        )
        result = self.api.get_variables("uc-1")
        assert result == {"url": "https://example.com"}

    def test_get_variables_dict_format(self):
        self.client._session.request.return_value = _mock_response(
            200, {"variables": {"url": "https://example.com"}}
        )
        result = self.api.get_variables("uc-1")
        assert result == {"url": "https://example.com"}

    def test_get_variables_empty(self):
        self.client._session.request.return_value = _mock_response(200, {"variables": []})
        result = self.api.get_variables("uc-1")
        assert result == {}

    def test_get_secrets(self):
        self.client._session.request.return_value = _mock_response(200, {"secrets": [{"key": "api_key"}]})
        result = self.api.get_secrets("uc-1")
        assert result == [{"key": "api_key"}]

    def test_create_execution_minimal(self):
        self.client._session.request.return_value = _mock_response(200, {"execution_id": "ex-1"})
        result = self.api.create_execution("uc-1")
        assert result["execution_id"] == "ex-1"
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("POST", "https://api.example.com/api/usecase/uc-1/execute")

    def test_create_execution_with_overrides(self):
        self.client._session.request.return_value = _mock_response(200, {"execution_id": "ex-1"})
        self.api.create_execution(
            "uc-1",
            base_url="https://staging.example.com",
            variables={"env": "staging"},
            region="us-west-2",
            model_id="model-v2",
        )
        call_args = self.client._session.request.call_args
        body = call_args[1]["json"]
        assert body["base_url"] == "https://staging.example.com"
        assert body["variables"] == {"env": "staging"}
        assert body["region"] == "us-west-2"
        assert body["model_id"] == "model-v2"


# ---------------------------------------------------------------------------
# ExecutionAPI tests
# ---------------------------------------------------------------------------

class TestExecutionAPI:
    def setup_method(self):
        self.client = _make_client()
        self.api = ExecutionAPI(self.client)

    def test_get_execution(self):
        """get_execution composes data from 3 API calls."""
        responses = [
            _mock_response(200, {"execution_id": "ex-1", "status": "running"}),
            _mock_response(200, {"steps": [{"id": "s1"}]}),
            _mock_response(200, {"execution_variables": {"env": "prod"}}),
        ]
        self.client._session.request.side_effect = responses
        result = asyncio.run(self.api.get_execution("uc-1", "ex-1"))
        assert result["execution_id"] == "ex-1"
        assert result["steps"] == [{"id": "s1"}]
        assert result["variables"] == {"env": "prod"}

    def test_get_execution_falls_back_to_variables_list(self):
        responses = [
            _mock_response(200, {"execution_id": "ex-1"}),
            _mock_response(200, {"steps": []}),
            _mock_response(200, {"execution_variables": {}, "variables": [{"key": "k", "value": "v"}]}),
        ]
        self.client._session.request.side_effect = responses
        result = asyncio.run(self.api.get_execution("uc-1", "ex-1"))
        assert result["variables"] == {"k": "v"}

    def test_update_status(self):
        self.client._session.request.return_value = _mock_response(200, {"ok": True})
        result = asyncio.run(self.api.update_status("uc-1", "ex-1", "failed", error_message="boom"))
        assert result == {"ok": True}
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("PATCH", "https://api.example.com/api/usecase/uc-1/executions/ex-1/status")
        body = call_args[1]["json"]
        assert body["status"] == "failed"
        assert body["error_message"] == "boom"

    def test_update_suite_status(self):
        self.client._session.request.return_value = _mock_response(200, {"ok": True})
        result = asyncio.run(self.api.update_suite_status("suite-1", "se-1", "success"))
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("PATCH", "https://api.example.com/api/test-suites/suite-1/executions/se-1/status")

    def test_update_step_status(self):
        self.client._session.request.return_value = _mock_response(200, {"ok": True})
        result = asyncio.run(
            self.api.update_step_status(
                "uc-1", "ex-1", "step-1", "success",
                actual_value="42", act_id="act-abc", logs="step done",
            )
        )
        call_args = self.client._session.request.call_args
        body = call_args[1]["json"]
        assert body["status"] == "success"
        assert body["actual_value"] == "42"
        assert body["act_id"] == "act-abc"
        assert body["logs"] == "step done"

    def test_update_session_id(self):
        self.client._session.request.return_value = _mock_response(200, {"ok": True})
        asyncio.run(self.api.update_session_id("uc-1", "ex-1", "sess-123"))
        call_args = self.client._session.request.call_args
        body = call_args[1]["json"]
        assert body["status"] == "running"
        assert body["nova_session_id"] == "sess-123"

    def test_get_secret_value(self):
        self.client._session.request.return_value = _mock_response(200, {"value": "secret-val"})
        result = self.api.get_secret_value("uc-1", "api_key")
        assert result == "secret-val"

    def test_get_secret_value_returns_none_on_error(self):
        self.client._session.request.side_effect = Exception("not found")
        result = self.api.get_secret_value("uc-1", "missing")
        assert result is None


# ---------------------------------------------------------------------------
# TestSuiteAPI tests
# ---------------------------------------------------------------------------

class TestTestSuiteAPI:
    def setup_method(self):
        self.client = _make_client()
        self.api = TestSuiteAPI(self.client)

    def test_get_suite(self):
        self.client._session.request.return_value = _mock_response(200, {"id": "s-1", "name": "Regression"})
        result = self.api.get_suite("s-1")
        assert result["name"] == "Regression"
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("GET", "https://api.example.com/api/test-suites/s-1")

    def test_execute_suite_minimal(self):
        self.client._session.request.return_value = _mock_response(200, {"suite_execution_id": "se-1"})
        result = self.api.execute_suite("s-1")
        assert result["suite_execution_id"] == "se-1"
        call_args = self.client._session.request.call_args
        body = call_args[1]["json"]
        assert body["trigger_type"] == "ci_runner"

    def test_execute_suite_with_overrides(self):
        self.client._session.request.return_value = _mock_response(200, {"suite_execution_id": "se-1"})
        self.api.execute_suite(
            "s-1",
            base_url="https://staging.example.com",
            variables={"env": "staging"},
            region="eu-west-1",
            model_id="model-v3",
        )
        call_args = self.client._session.request.call_args
        body = call_args[1]["json"]
        assert body["base_url"] == "https://staging.example.com"
        assert body["variables"] == {"env": "staging"}
        assert body["region"] == "eu-west-1"
        assert body["model_id"] == "model-v3"

    def test_list_usecases(self):
        self.client._session.request.return_value = _mock_response(
            200, {"usecases": [{"usecase_id": "uc-1"}, {"usecase_id": "uc-2"}]}
        )
        result = self.api.list_usecases("s-1")
        assert len(result) == 2
        assert result[0]["usecase_id"] == "uc-1"


# ---------------------------------------------------------------------------
# Verify /api prefix in all paths
# ---------------------------------------------------------------------------

class TestApiPrefixInPaths:
    """All runner API modules must use /api prefix in request paths."""

    def test_usecase_api_paths_have_api_prefix(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"steps": [], "variables": [], "secrets": []})
        api = UseCaseAPI(client)

        api.get_usecase("uc-1")
        url = client._session.request.call_args[0][1]
        assert "/api/usecase/" in url

    def test_execution_api_paths_have_api_prefix(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"ok": True})
        api = ExecutionAPI(client)

        asyncio.run(api.update_status("uc-1", "ex-1", "running"))
        url = client._session.request.call_args[0][1]
        assert "/api/usecase/" in url

    def test_test_suite_api_paths_have_api_prefix(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"usecases": []})
        api = TestSuiteAPI(client)

        api.list_usecases("s-1")
        url = client._session.request.call_args[0][1]
        assert "/api/test-suites/" in url
