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

    def test_list_usecases(self):
        self.client._session.request.return_value = _mock_response(
            200, {"usecases": [{"id": "uc-1"}, {"id": "uc-2"}]}
        )
        result = self.api.list_usecases()
        assert [item["id"] for item in result] == ["uc-1", "uc-2"]
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("GET", "https://api.example.com/usecases")

    def test_list_usecases_missing_key(self):
        self.client._session.request.return_value = _mock_response(200, {})
        assert self.api.list_usecases() == []

    def test_list_usecases_null_value(self):
        self.client._session.request.return_value = _mock_response(200, {"usecases": None})
        assert self.api.list_usecases() == []

    def test_list_executions_default_limit(self):
        self.client._session.request.return_value = _mock_response(
            200, {"executions": [{"execution_id": "e-1"}, {"execution_id": "e-2"}]}
        )
        result = self.api.list_executions("uc-1")
        assert [e["execution_id"] for e in result] == ["e-1", "e-2"]
        call_args = self.client._session.request.call_args
        assert call_args[0] == (
            "GET", "https://api.example.com/usecase/uc-1/executions"
        )
        # Default limit=20 is sent as a query param.
        assert call_args[1]["params"] == {"limit": 20}

    def test_list_executions_explicit_limit(self):
        self.client._session.request.return_value = _mock_response(
            200, {"executions": []}
        )
        self.api.list_executions("uc-1", limit=5)
        call_args = self.client._session.request.call_args
        assert call_args[1]["params"] == {"limit": 5}

    def test_list_executions_missing_key(self):
        self.client._session.request.return_value = _mock_response(200, {})
        assert self.api.list_executions("uc-1") == []

    def test_get_usecase(self):
        self.client._session.request.return_value = _mock_response(200, {"id": "uc-1", "name": "Test"})
        result = self.api.get_usecase("uc-1")
        assert result["id"] == "uc-1"
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("GET", "https://api.example.com/usecase/uc-1")

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
        self.client._session.request.return_value = _mock_response(200, {"executionId": "ex-1"})
        result = self.api.create_execution("uc-1")
        assert result["executionId"] == "ex-1"
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("POST", "https://api.example.com/usecase/uc-1/execute")
        assert call_args[1]["params"] == {"trigger-type": "ci_runner"}

    def test_create_execution_with_overrides(self):
        self.client._session.request.return_value = _mock_response(200, {"executionId": "ex-1"})
        self.api.create_execution(
            "uc-1",
            base_url="https://staging.example.com",
            variables={"env": "staging"},
            region="us-west-2",
            model_id="model-v2",
        )
        call_args = self.client._session.request.call_args
        assert call_args[1]["params"] == {"trigger-type": "ci_runner"}
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
        assert call_args[0] == ("PATCH", "https://api.example.com/usecase/uc-1/executions/ex-1/status")
        body = call_args[1]["json"]
        assert body["status"] == "failed"
        assert body["error_message"] == "boom"

    def test_update_suite_status(self):
        self.client._session.request.return_value = _mock_response(200, {"ok": True})
        result = asyncio.run(self.api.update_suite_status("suite-1", "se-1", "success"))
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("PATCH", "https://api.example.com/test-suites/suite-1/executions/se-1/status")

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

    def test_create_runtime_variable_sends_correct_request(self):
        """R-API-1 consumer: POST {key, value} to the runtime-variables route."""
        self.client._session.request.return_value = _mock_response(
            200, {"status": "ok", "key": "orderId"},
        )
        result = asyncio.run(
            self.api.create_runtime_variable("uc-1", "ex-1", "orderId", "ORD-42"),
        )
        assert result == {"status": "ok", "key": "orderId"}
        call_args = self.client._session.request.call_args
        assert call_args[0] == (
            "POST",
            "https://api.example.com/usecase/uc-1/executions/ex-1/runtime-variables",
        )
        assert call_args[1]["json"] == {"key": "orderId", "value": "ORD-42"}

    def test_create_runtime_variable_propagates_server_errors(self):
        """Server failure must raise so the caller can decide to log + continue."""
        self.client._session.request.side_effect = Exception("500 Internal")
        with pytest.raises(Exception, match="500 Internal"):
            asyncio.run(
                self.api.create_runtime_variable("uc-1", "ex-1", "k", "v"),
            )

    # ---- R-API-5 consumer: trajectory URLs ------------------------------

    def test_get_trajectory_download_url_returns_url(self):
        self.client._session.request.return_value = _mock_response(
            200, {"download_url": "https://s3.example/get?sig=xyz", "expires_in": 900},
        )
        url = self.api.get_trajectory_download_url("uc-1", "step-1")
        assert url == "https://s3.example/get?sig=xyz"
        call_args = self.client._session.request.call_args
        assert call_args[0] == (
            "GET",
            "https://api.example.com/usecase/uc-1/steps/step-1/trajectory/download-url",
        )

    def test_get_trajectory_download_url_returns_none_on_404(self):
        """A missing trajectory is expected — callers skip replay, not error."""
        self.client._session.request.side_effect = Exception("HTTP 404 Not Found")
        url = self.api.get_trajectory_download_url("uc-1", "step-1")
        assert url is None

    def test_get_trajectory_download_url_reraises_non_404(self):
        self.client._session.request.side_effect = Exception("500 Internal Server Error")
        with pytest.raises(Exception, match="500"):
            self.api.get_trajectory_download_url("uc-1", "step-1")

    def test_create_trajectory_upload_url_returns_payload(self):
        self.client._session.request.return_value = _mock_response(
            200,
            {
                "upload_url": "https://s3.example/put",
                "s3_key": "uc-1/trajectories/step-1.json",
                "expires_in": 900,
            },
        )
        payload = self.api.create_trajectory_upload_url("uc-1", "step-1")
        assert payload is not None
        assert payload["upload_url"] == "https://s3.example/put"
        assert payload["s3_key"] == "uc-1/trajectories/step-1.json"
        call_args = self.client._session.request.call_args
        assert call_args[0] == (
            "POST",
            "https://api.example.com/usecase/uc-1/steps/step-1/trajectory/upload-url",
        )
        assert call_args[1]["json"] == {"content_type": "application/json"}

    def test_create_trajectory_upload_url_returns_none_on_failure(self):
        """Best-effort save: API failure yields None so save_trajectory skips."""
        self.client._session.request.side_effect = Exception("503 Service Unavailable")
        payload = self.api.create_trajectory_upload_url("uc-1", "step-1")
        assert payload is None

    # ---- R-API-6 consumer: clear_cache_fields on step status ------------

    def test_update_step_status_passes_clear_cache_fields(self):
        self.client._session.request.return_value = _mock_response(200, {"ok": True})
        asyncio.run(
            self.api.update_step_status(
                "uc-1", "ex-1", "step-1", "failed",
                clear_cache_fields=["trajectory_s3_key", "trajectory_last_updated"],
            )
        )
        body = self.client._session.request.call_args[1]["json"]
        assert body["clear_cache_fields"] == [
            "trajectory_s3_key", "trajectory_last_updated",
        ]

    def test_update_step_status_omits_clear_cache_fields_when_empty(self):
        self.client._session.request.return_value = _mock_response(200, {"ok": True})
        asyncio.run(
            self.api.update_step_status(
                "uc-1", "ex-1", "step-1", "success", clear_cache_fields=[],
            )
        )
        body = self.client._session.request.call_args[1]["json"]
        assert "clear_cache_fields" not in body

    def test_update_step_status_omits_clear_cache_fields_when_none(self):
        self.client._session.request.return_value = _mock_response(200, {"ok": True})
        asyncio.run(
            self.api.update_step_status("uc-1", "ex-1", "step-1", "success"),
        )
        body = self.client._session.request.call_args[1]["json"]
        assert "clear_cache_fields" not in body

    # ---- R-API-2 consumer: live-view publish/delete ---------------------

    def test_create_live_view_posts_url(self):
        self.client._session.request.return_value = _mock_response(
            200, {"status": "ok"},
        )
        result = asyncio.run(
            self.api.create_live_view("uc-1", "ex-1", "https://live.example/abc"),
        )
        assert result == {"status": "ok"}
        call_args = self.client._session.request.call_args
        assert call_args[0] == (
            "POST",
            "https://api.example.com/usecase/uc-1/executions/ex-1/live-view",
        )
        assert call_args[1]["json"] == {"live_view_url": "https://live.example/abc"}

    def test_create_live_view_propagates_server_errors(self):
        self.client._session.request.side_effect = Exception("500 Internal")
        with pytest.raises(Exception, match="500"):
            asyncio.run(
                self.api.create_live_view("uc-1", "ex-1", "https://x.test/"),
            )

    def test_delete_live_view_swallows_404(self):
        """404 means nothing was published — treat as already-clean."""
        self.client._session.request.side_effect = Exception("HTTP 404 Not Found")
        # Should not raise.
        asyncio.run(self.api.delete_live_view("uc-1", "ex-1"))

    def test_delete_live_view_propagates_other_errors(self):
        self.client._session.request.side_effect = Exception("500 Internal Server Error")
        with pytest.raises(Exception, match="500"):
            asyncio.run(self.api.delete_live_view("uc-1", "ex-1"))

    def test_delete_live_view_sends_delete(self):
        self.client._session.request.return_value = _mock_response(204, None)
        asyncio.run(self.api.delete_live_view("uc-1", "ex-1"))
        call_args = self.client._session.request.call_args
        assert call_args[0] == (
            "DELETE",
            "https://api.example.com/usecase/uc-1/executions/ex-1/live-view",
        )

    # ---- R-API-3 consumer: update_mobile_metadata -----------------------

    def test_update_mobile_metadata_session_arn_only(self):
        self.client._session.request.return_value = _mock_response(
            200, {"status": "ok"},
        )
        asyncio.run(
            self.api.update_mobile_metadata(
                "uc-1", "ex-1",
                device_farm_session_arn="arn:aws:devicefarm:us-west-2:1:session:abc",
            )
        )
        call_args = self.client._session.request.call_args
        assert call_args[0] == (
            "PATCH",
            "https://api.example.com/usecase/uc-1/executions/ex-1/mobile-metadata",
        )
        assert call_args[1]["json"] == {
            "device_farm_session_arn": "arn:aws:devicefarm:us-west-2:1:session:abc",
        }

    def test_update_mobile_metadata_all_fields(self):
        self.client._session.request.return_value = _mock_response(200, {"status": "ok"})
        asyncio.run(
            self.api.update_mobile_metadata(
                "uc-1", "ex-1",
                device_farm_session_arn="arn:aws:devicefarm:us-west-2:1:session:a",
                device_name="Pixel 6",
                device_os_version="Android 13",
            )
        )
        body = self.client._session.request.call_args[1]["json"]
        assert body == {
            "device_farm_session_arn": "arn:aws:devicefarm:us-west-2:1:session:a",
            "device_name": "Pixel 6",
            "device_os_version": "Android 13",
        }

    def test_update_mobile_metadata_empty_payload_raises(self):
        """No kwargs given → ValueError before any request goes out."""
        with pytest.raises(ValueError, match="at least one field"):
            asyncio.run(self.api.update_mobile_metadata("uc-1", "ex-1"))
        self.client._session.request.assert_not_called()

    def test_update_mobile_metadata_propagates_server_errors(self):
        self.client._session.request.side_effect = Exception("500 Internal")
        with pytest.raises(Exception, match="500"):
            asyncio.run(
                self.api.update_mobile_metadata(
                    "uc-1", "ex-1", device_name="Pixel 6",
                )
            )

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

    def test_list_suites(self):
        self.client._session.request.return_value = _mock_response(
            200, {"suites": [{"id": "s-1"}, {"id": "s-2"}]}
        )
        result = self.api.list_suites()
        assert [item["id"] for item in result] == ["s-1", "s-2"]
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("GET", "https://api.example.com/test-suites")

    def test_list_suites_missing_key(self):
        self.client._session.request.return_value = _mock_response(200, {})
        assert self.api.list_suites() == []

    def test_get_suite(self):
        self.client._session.request.return_value = _mock_response(200, {"id": "s-1", "name": "Regression"})
        result = self.api.get_suite("s-1")
        assert result["name"] == "Regression"
        call_args = self.client._session.request.call_args
        assert call_args[0] == ("GET", "https://api.example.com/test-suites/s-1")

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
# Verify paths match API Gateway routes (no /api prefix)
# ---------------------------------------------------------------------------

class TestApiPathsMatchRoutes:
    """All runner API modules must use paths matching API Gateway routes."""

    def test_usecase_api_paths_use_correct_prefix(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"steps": [], "variables": [], "secrets": []})
        api = UseCaseAPI(client)

        api.get_usecase("uc-1")
        url = client._session.request.call_args[0][1]
        assert "/usecase/" in url
        assert "/api/usecase/" not in url

    def test_execution_api_paths_use_correct_prefix(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"ok": True})
        api = ExecutionAPI(client)

        asyncio.run(api.update_status("uc-1", "ex-1", "running"))
        url = client._session.request.call_args[0][1]
        assert "/usecase/" in url
        assert "/api/usecase/" not in url

    def test_test_suite_api_paths_use_correct_prefix(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"usecases": []})
        api = TestSuiteAPI(client)

        api.list_usecases("s-1")
        url = client._session.request.call_args[0][1]
        assert "/test-suites/" in url
        assert "/api/test-suites/" not in url
