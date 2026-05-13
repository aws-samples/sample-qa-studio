"""Unit tests for :mod:`qa_studio_cli.tui.api`.

No Textual dependency — these tests mock the underlying ``ApiClient``
and assert the facade's dict/list shapes. Runs in the base dev venv
without ``[tui]``.
"""

from unittest.mock import MagicMock

from qa_studio_cli.tui.api import TuiApi, UsecaseListItem, SuiteListItem, ExecutionListItem


class TestUsecaseListItemFromApi:
    def test_accepts_snake_case_id(self):
        item = UsecaseListItem.from_api(
            {"usecase_id": "u-1", "name": "Login", "test_platform": "web",
             "executing_region": "us-east-1"}
        )
        assert item.usecase_id == "u-1"
        assert item.name == "Login"
        assert item.platform == "web"
        assert item.region == "us-east-1"

    def test_accepts_plain_id_field(self):
        item = UsecaseListItem.from_api({"id": "u-2", "name": "Checkout"})
        assert item.usecase_id == "u-2"

    def test_falls_back_on_missing_fields(self):
        item = UsecaseListItem.from_api({})
        assert item.usecase_id == ""
        assert item.name == "—"
        assert item.platform == "web"
        assert item.region == "—"

    def test_prefers_test_platform_over_platform(self):
        """API inconsistency: some endpoints return 'platform', some 'test_platform'."""
        item = UsecaseListItem.from_api({"id": "x", "test_platform": "mobile"})
        assert item.platform == "mobile"


class TestTuiApiListUsecases:
    def test_happy_path(self):
        client = MagicMock()
        client.get.return_value = {
            "usecases": [
                {"id": "u-1", "name": "Login"},
                {"id": "u-2", "name": "Checkout", "test_platform": "mobile"},
            ],
        }
        api = TuiApi(client)
        items = api.list_usecases()
        assert [i.usecase_id for i in items] == ["u-1", "u-2"]
        assert items[1].platform == "mobile"
        client.get.assert_called_once_with("/usecases")

    def test_missing_usecases_key_returns_empty_list(self):
        client = MagicMock()
        client.get.return_value = {}
        api = TuiApi(client)
        assert api.list_usecases() == []

    def test_null_usecases_value_returns_empty_list(self):
        client = MagicMock()
        client.get.return_value = {"usecases": None}
        api = TuiApi(client)
        assert api.list_usecases() == []


class TestTuiApiSubresources:
    def test_get_usecase_delegates_to_usecase_api(self):
        client = MagicMock()
        client.get.return_value = {"name": "Checkout", "id": "u-1"}
        api = TuiApi(client)
        result = api.get_usecase("u-1")
        assert result["name"] == "Checkout"
        client.get.assert_called_with("/usecase/u-1")

    def test_get_steps_extracts_list(self):
        client = MagicMock()
        client.get.return_value = {"steps": [{"sort": 1}]}
        api = TuiApi(client)
        assert api.get_steps("u-1") == [{"sort": 1}]

    def test_get_variables_returns_dict(self):
        client = MagicMock()
        client.get.return_value = {
            "variables": [{"key": "email", "value": "x@example.com"}],
        }
        api = TuiApi(client)
        assert api.get_variables("u-1") == {"email": "x@example.com"}

    def test_get_headers_tolerates_api_error(self):
        """A 404 on headers sub-resource must not break the detail screen."""
        client = MagicMock()
        client.get.side_effect = RuntimeError("404 not found")
        api = TuiApi(client)
        assert api.get_headers("u-1") == {}

    def test_get_secrets_tolerates_api_error(self):
        client = MagicMock()
        client.get.side_effect = RuntimeError("500 internal")
        api = TuiApi(client)
        assert api.get_secrets("u-1") == []


class TestSuiteListItemFromApi:
    def test_happy_path(self):
        item = SuiteListItem.from_api(
            {"id": "s-1", "name": "Smoke", "total_usecases": 4,
             "description": "Happy paths"}
        )
        assert item.suite_id == "s-1"
        assert item.name == "Smoke"
        assert item.total_usecases == 4
        assert item.description == "Happy paths"

    def test_accepts_suite_id_alias(self):
        item = SuiteListItem.from_api({"suite_id": "s-2", "name": "Regr."})
        assert item.suite_id == "s-2"

    def test_defaults_when_fields_missing(self):
        item = SuiteListItem.from_api({})
        assert item.suite_id == ""
        assert item.name == "—"
        assert item.total_usecases == 0
        assert item.description == ""


class TestTuiApiListSuites:
    def test_happy_path(self):
        client = MagicMock()
        client.get.return_value = {
            "suites": [
                {"id": "s-1", "name": "Smoke", "total_usecases": 3},
                {"id": "s-2", "name": "Full regression", "total_usecases": 42},
            ],
        }
        api = TuiApi(client)
        items = api.list_suites()
        assert [i.suite_id for i in items] == ["s-1", "s-2"]
        assert items[1].total_usecases == 42
        client.get.assert_called_once_with("/test-suites")

    def test_missing_suites_key_returns_empty_list(self):
        client = MagicMock()
        client.get.return_value = {}
        api = TuiApi(client)
        assert api.list_suites() == []


class TestTuiApiSuiteDetail:
    def test_get_suite_delegates(self):
        client = MagicMock()
        client.get.return_value = {"name": "Smoke", "id": "s-1"}
        api = TuiApi(client)
        result = api.get_suite("s-1")
        assert result["name"] == "Smoke"
        client.get.assert_called_with("/test-suites/s-1")

    def test_list_suite_usecases_extracts_list(self):
        client = MagicMock()
        client.get.return_value = {"usecases": [{"id": "u-1", "order": 1}]}
        api = TuiApi(client)
        result = api.list_suite_usecases("s-1")
        assert result == [{"id": "u-1", "order": 1}]



class TestExecutionListItemFromApi:
    def test_happy_path(self):
        item = ExecutionListItem.from_api(
            {
                "execution_id": "e-1",
                "status": "success",
                "created_at": "2024-02-20T10:00:00Z",
                "duration_seconds": 42.5,
                "trigger_type": "ci_runner",
                "triggered_by": "alice",
            }
        )
        assert item.execution_id == "e-1"
        assert item.status == "success"
        assert item.duration_seconds == 42.5
        assert item.trigger_type == "ci_runner"
        assert item.triggered_by == "alice"

    def test_accepts_id_alias(self):
        item = ExecutionListItem.from_api({"id": "e-alt"})
        assert item.execution_id == "e-alt"

    def test_extracts_execution_id_from_ddb_sk(self):
        """Regression: ``list_executions`` returns raw DynamoDB items
        where the execution id only lives in the sort key
        (``sk = 'EXECUTION#<id>'``). Missing the id here made the row
        key ``None`` and broke row selection on the Executions tab."""
        item = ExecutionListItem.from_api(
            {"sk": "EXECUTION#abc-123", "status": "success"}
        )
        assert item.execution_id == "abc-123"

    def test_explicit_id_wins_over_sk(self):
        """If both are present the explicit id wins — future-proofs
        against the server eventually promoting the id to a field."""
        item = ExecutionListItem.from_api(
            {"id": "e-explicit", "sk": "EXECUTION#e-from-sk"}
        )
        assert item.execution_id == "e-explicit"

    def test_defaults_on_missing_fields(self):
        item = ExecutionListItem.from_api({})
        assert item.execution_id == ""
        assert item.status == "—"
        assert item.duration_seconds == 0.0

    def test_duration_plain_seconds_key(self):
        """Some payloads use ``duration`` rather than ``duration_seconds``."""
        item = ExecutionListItem.from_api({"duration": 17})
        assert item.duration_seconds == 17.0

    def test_non_numeric_duration_falls_back_to_zero(self):
        item = ExecutionListItem.from_api({"duration_seconds": "invalid"})
        assert item.duration_seconds == 0.0


class TestTuiApiListExecutions:
    def test_happy_path(self):
        client = MagicMock()
        client.get.return_value = {
            "executions": [
                {"execution_id": "e-1", "status": "success", "duration_seconds": 10},
                {"execution_id": "e-2", "status": "failed", "duration_seconds": 3},
            ],
        }
        api = TuiApi(client)
        items = api.list_executions("uc-1")
        assert [i.execution_id for i in items] == ["e-1", "e-2"]
        assert items[0].status == "success"
        client.get.assert_called_with(
            "/usecase/uc-1/executions", params={"limit": 20}
        )

    def test_tolerates_api_error(self):
        """A 404 on an older usecase must not break the rest of the
        detail load — empty list is the defined fallback."""
        client = MagicMock()
        client.get.side_effect = RuntimeError("404 not found")
        api = TuiApi(client)
        assert api.list_executions("uc-1") == []
