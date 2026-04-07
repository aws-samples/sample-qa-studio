"""Tests for the suites command group."""

import importlib
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner
from hypothesis import given, settings
from hypothesis import strategies as st

from qa_studio_cli.commands.suites import suites
from qa_studio_cli.models.api import SuiteModel
from qa_studio_cli.models.errors import ApiError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke_with_mock(runner, mock_client, args, input_text=None):
    """Invoke the suites CLI group with a mocked auth client."""
    from qa_studio_cli.commands import suites as suites_module
    from qa_studio_cli.api import client as client_module

    def fake_require_auth(fn):
        import functools

        @functools.wraps(fn)
        @click.pass_context
        def wrapper(ctx, *args, **kwargs):
            ctx.ensure_object(dict)
            ctx.obj["client"] = mock_client
            return ctx.invoke(fn, *args, **kwargs)

        return wrapper

    with patch.object(client_module, "require_auth", fake_require_auth):
        importlib.reload(suites_module)
        cli = click.Group()
        cli.add_command(suites_module.suites)
        result = runner.invoke(
            cli, ["suites"] + args, input=input_text, catch_exceptions=False
        )

    importlib.reload(suites_module)
    return result


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

suite_strategy = st.builds(
    SuiteModel,
    id=st.uuids().map(str),
    name=st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Zs"),
            min_codepoint=32,
            max_codepoint=126,
        ),
    ),
    description=st.text(
        max_size=50,
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    ),
    tags=st.lists(
        st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("L",)),
        ),
        max_size=3,
    ),
    created_at=st.from_regex(
        r"2024-0[1-9]-[012][0-9]T[01][0-9]:[0-5][0-9]:[0-5][0-9]Z",
        fullmatch=True,
    ),
    created_by=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=48, max_codepoint=122),
    ),
    total_usecases=st.integers(min_value=0, max_value=100),
)


# ---------------------------------------------------------------------------
# Property test: List output contains all resource identifiers (Property 7)
# Sub-task 7.2
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 7: List output contains all resource identifiers (suites)
# **Validates: Requirements 7.2**
class TestSuiteListOutputProperty:
    """For any non-empty list of SuiteModel instances, CLI output contains every suite's name, id, and total_usecases."""

    @given(items=st.lists(suite_strategy, min_size=1, max_size=5))
    @settings(max_examples=100)
    def test_list_output_contains_all_names_ids_and_totals(self, items):
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "suites": [item.model_dump(by_alias=True) for item in items]
        }

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["list"])

        assert result.exit_code == 0
        for item in items:
            assert item.name in result.output
            assert item.id in result.output
            assert str(item.total_usecases) in result.output


# ---------------------------------------------------------------------------
# Property test: Detail output contains all specified fields (Property 8)
# Sub-task 7.3
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 8: Detail output contains all specified fields (suites)
# **Validates: Requirements 8.2**
class TestSuiteDetailOutputProperty:
    """For any SuiteModel with non-empty fields, CLI output of suites get contains all fields."""

    @given(item=suite_strategy)
    @settings(max_examples=100)
    def test_get_output_contains_all_fields(self, item):
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            item.model_dump(by_alias=True),
            {"usecases": [], "total": 0},
        ]

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["get", item.id])

        assert result.exit_code == 0
        assert item.name in result.output
        assert item.description in result.output
        assert str(item.total_usecases) in result.output
        assert item.created_by in result.output
        assert item.created_at in result.output
        for tag in item.tags:
            assert tag in result.output


# ---------------------------------------------------------------------------
# Property test: Suite run override flags map to request body (Property 10)
# Sub-task 7.4
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 10: Suite run override flags map to request body
# **Validates: Requirements 12.2**
class TestSuiteRunOverrideProperty:
    """For any combination of override flags, the POST body contains corresponding fields and trigger_type is always ci_runner."""

    @given(
        base_url=st.one_of(st.none(), st.from_regex(r"https://[a-z]{1,10}\.[a-z]{2,4}", fullmatch=True)),
        region=st.one_of(st.none(), st.sampled_from(["us-east-1", "eu-west-1", "ap-southeast-1"])),
        model_id=st.one_of(st.none(), st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Pd")))),
        var_keys=st.lists(
            st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L",))),
            max_size=3,
            unique=True,
        ),
        var_values=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(min_codepoint=32, max_codepoint=126)),
            max_size=3,
        ),
    )
    @settings(max_examples=100)
    def test_run_override_flags_map_to_request_body(self, base_url, region, model_id, var_keys, var_values):
        # Build matching key-value pairs
        pairs = list(zip(var_keys, var_values))

        mock_client = MagicMock()
        mock_client.post.return_value = {
            "suiteExecutionId": "exec-123",
            "suiteId": "suite-abc",
            "status": "running",
            "createdAt": "2024-01-01T00:00:00Z",
            "executionIds": [],
        }

        args = ["run", "suite-abc"]
        if base_url:
            args += ["--base-url", base_url]
        if region:
            args += ["--region", region]
        if model_id:
            args += ["--model-id", model_id]
        for k, v in pairs:
            args += ["--var", f"{k}={v}"]

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, args)

        assert result.exit_code == 0

        # Verify the POST body
        call_args = mock_client.post.call_args
        body = call_args[1]["json_body"]

        assert body["trigger_type"] == "ci_runner"

        if base_url or region or model_id or pairs:
            overrides = body.get("overrides", {})
            if base_url:
                assert overrides["base_url"] == base_url
            if region:
                assert overrides["region"] == region
            if model_id:
                assert overrides["model_id"] == model_id
            if pairs:
                for k, v in pairs:
                    assert overrides["variables"][k] == v


# ---------------------------------------------------------------------------
# Property test: Empty/whitespace suite name rejected client-side (Property 11)
# Sub-task 7.5
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 11: Empty/whitespace suite name rejected client-side
# **Validates: Requirements 9.4**
class TestSuiteEmptyNameProperty:
    """For any whitespace-only string, suites create --name <that string> shows validation error and exits non-zero without API call."""

    @given(
        name=st.from_regex(r"[ \t\n\r]*", fullmatch=True).filter(lambda s: len(s) <= 20),
    )
    @settings(max_examples=100)
    def test_empty_whitespace_name_rejected(self, name):
        mock_client = MagicMock()

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            ["create", "--name", name, "--description", "some desc"],
        )

        assert result.exit_code != 0
        assert "empty" in result.output.lower() or "whitespace" in result.output.lower()
        mock_client.post.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests for suites commands (Sub-task 7.6)
# ---------------------------------------------------------------------------


class TestSuiteListCommand:
    """Unit tests for suites list command."""

    def test_displays_table_with_names_ids_and_totals(self):
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "suites": [
                {"id": "suite-001", "name": "Smoke Tests", "totalUsecases": 5},
                {"id": "suite-002", "name": "Regression", "totalUsecases": 12},
            ]
        }

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["list"])

        assert result.exit_code == 0
        assert "Smoke Tests" in result.output
        assert "suite-001" in result.output
        assert "5" in result.output
        assert "Regression" in result.output
        assert "suite-002" in result.output
        assert "12" in result.output

    def test_shows_no_suites_found_for_empty_response(self):
        mock_client = MagicMock()
        mock_client.get.return_value = {"suites": []}

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["list"])

        assert result.exit_code == 0
        assert "No suites found" in result.output


class TestSuiteGetCommand:
    """Unit tests for suites get command."""

    def test_displays_all_suite_fields(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            {
                "id": "suite-001",
                "name": "Smoke Tests",
                "description": "Core smoke test suite",
                "tags": ["smoke", "core"],
                "totalUsecases": 5,
                "createdBy": "user@example.com",
                "createdAt": "2024-03-15T10:00:00Z",
            },
            {
                "usecases": [
                    {"usecase_id": "uc-1", "usecase_name": "Login Flow", "added_by": "user@example.com", "added_at": "2024-03-15T10:00:00Z"},
                    {"usecase_id": "uc-2", "usecase_name": "Checkout", "added_by": "user@example.com", "added_at": "2024-03-15T11:00:00Z"},
                ],
                "total": 2,
            },
        ]

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["get", "suite-001"])

        assert result.exit_code == 0
        assert "Smoke Tests" in result.output
        assert "Core smoke test suite" in result.output
        assert "smoke" in result.output
        assert "core" in result.output
        assert "5" in result.output
        assert "user@example.com" in result.output
        assert "2024-03-15T10:00:00Z" in result.output
        assert "Usecases (2):" in result.output
        assert "uc-1" in result.output
        assert "Login Flow" in result.output
        assert "uc-2" in result.output
        assert "Checkout" in result.output

    def test_displays_no_usecases_message(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            {
                "id": "suite-001",
                "name": "Empty Suite",
                "description": "",
                "tags": [],
                "totalUsecases": 0,
                "createdBy": "user@example.com",
                "createdAt": "2024-03-15T10:00:00Z",
            },
            {"usecases": [], "total": 0},
        ]

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["get", "suite-001"])

        assert result.exit_code == 0
        assert "No usecases in this suite." in result.output

    def test_shows_not_found_on_404(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = ApiError(404, "Resource not found.")

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["get", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestSuiteCreateCommand:
    """Unit tests for suites create command."""

    def test_sends_post_and_displays_result(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {"id": "suite-new", "name": "My Suite"}

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            ["create", "--name", "My Suite", "--description", "A test suite"],
        )

        assert result.exit_code == 0
        assert "suite-new" in result.output
        assert "My Suite" in result.output
        mock_client.post.assert_called_once()
        call_body = mock_client.post.call_args[1]["json_body"]
        assert call_body["name"] == "My Suite"
        assert call_body["description"] == "A test suite"

    def test_empty_name_shows_validation_error(self):
        mock_client = MagicMock()

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            ["create", "--name", "", "--description", "desc"],
        )

        assert result.exit_code != 0
        assert "empty" in result.output.lower() or "whitespace" in result.output.lower()
        mock_client.post.assert_not_called()

    def test_whitespace_name_shows_validation_error(self):
        mock_client = MagicMock()

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            ["create", "--name", "   ", "--description", "desc"],
        )

        assert result.exit_code != 0
        mock_client.post.assert_not_called()

    def test_sends_tags_array(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {"id": "suite-tagged", "name": "Tagged Suite"}

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            [
                "create",
                "--name", "Tagged Suite",
                "--description", "Suite with tags",
                "--tags", "smoke",
                "--tags", "regression",
            ],
        )

        assert result.exit_code == 0
        call_body = mock_client.post.call_args[1]["json_body"]
        assert call_body["tags"] == ["smoke", "regression"]


class TestSuiteAddTestsCommand:
    """Unit tests for suites add-tests command."""

    def test_sends_post_with_usecase_ids(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {"added": 2, "totalUsecases": 5}

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            ["add-tests", "suite-001", "uc-aaa", "uc-bbb"],
        )

        assert result.exit_code == 0
        assert "2" in result.output
        assert "5" in result.output
        call_body = mock_client.post.call_args[1]["json_body"]
        assert call_body["usecaseIds"] == ["uc-aaa", "uc-bbb"]

    def test_shows_not_found_on_404(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ApiError(404, "Resource not found.")

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            ["add-tests", "nonexistent", "uc-aaa"],
        )

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestSuiteRemoveTestCommand:
    """Unit tests for suites remove-test command."""

    def test_sends_delete_and_shows_confirmation(self):
        mock_client = MagicMock()
        mock_client.delete.return_value = None

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            ["remove-test", "suite-001", "uc-aaa"],
        )

        assert result.exit_code == 0
        assert "Removed" in result.output
        assert "uc-aaa" in result.output
        mock_client.delete.assert_called_once_with(
            "/api/test-suites/suite-001/usecases/uc-aaa"
        )

    def test_shows_not_found_on_404(self):
        mock_client = MagicMock()
        mock_client.delete.side_effect = ApiError(404, "Resource not found.")

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            ["remove-test", "suite-001", "uc-aaa"],
        )

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestSuiteRunCommand:
    """Unit tests for suites run command."""

    def test_sends_post_with_trigger_type_ci_runner(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {
            "suiteExecutionId": "se-001",
            "suiteId": "suite-001",
            "status": "running",
            "createdAt": "2024-01-01T00:00:00Z",
            "executionIds": [{"usecaseId": "uc-1"}, {"usecaseId": "uc-2"}],
        }

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["run", "suite-001"])

        assert result.exit_code == 0
        assert "se-001" in result.output
        assert "2" in result.output
        call_body = mock_client.post.call_args[1]["json_body"]
        assert call_body["trigger_type"] == "ci_runner"

    def test_includes_overrides_in_body(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {
            "suiteExecutionId": "se-002",
            "suiteId": "suite-001",
            "status": "running",
            "createdAt": "2024-01-01T00:00:00Z",
            "executionIds": [{"usecaseId": "uc-1"}],
        }

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            [
                "run", "suite-001",
                "--base-url", "https://staging.example.com",
                "--var", "USER=admin",
                "--var", "PASS=secret",
                "--region", "eu-west-1",
                "--model-id", "us.amazon.nova-2-lite-v1:0",
            ],
        )

        assert result.exit_code == 0
        call_body = mock_client.post.call_args[1]["json_body"]
        assert call_body["trigger_type"] == "ci_runner"
        overrides = call_body["overrides"]
        assert overrides["base_url"] == "https://staging.example.com"
        assert overrides["region"] == "eu-west-1"
        assert overrides["model_id"] == "us.amazon.nova-2-lite-v1:0"
        assert overrides["variables"]["USER"] == "admin"
        assert overrides["variables"]["PASS"] == "secret"

    def test_shows_error_on_empty_suite_400(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ApiError(400, "Test suite contains no usecases")

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["run", "suite-empty"])

        assert result.exit_code == 1
        assert "no usecases" in result.output.lower()

    def test_shows_error_on_unresolved_variables_400(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ApiError(
            400, "Unresolved variables: BASE_URL, API_KEY"
        )

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["run", "suite-vars"])

        assert result.exit_code == 1
        assert "unresolved variables" in result.output.lower()
