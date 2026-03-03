"""Tests for the tests (usecase) command group."""

from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner
from hypothesis import given, settings
from hypothesis import strategies as st

from qa_studio_cli.commands.tests import tests
from qa_studio_cli.models.api import UsecaseModel
from qa_studio_cli.models.errors import ApiError


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_cli_group():
    """Create a CLI group with the tests subgroup registered."""
    cli = click.Group()
    cli.add_command(tests)
    return cli


def _patch_auth(mock_client):
    """Return a context manager that patches require_auth to inject mock_client."""
    return patch(
        "qa_studio_cli.commands.tests.require_auth",
        lambda fn: _bypass_auth(fn, mock_client),
    )


def _bypass_auth(fn, mock_client):
    """Wrap a Click command to bypass require_auth and inject a mock client."""
    import functools

    @functools.wraps(fn)
    @click.pass_context
    def wrapper(ctx, *args, **kwargs):
        ctx.ensure_object(dict)
        ctx.obj["client"] = mock_client
        return ctx.invoke(fn, *args, **kwargs)

    return wrapper


def _invoke_with_mock(runner, mock_client, args, input_text=None):
    """Invoke the tests CLI group with a mocked auth client."""
    # We need to rebuild the command group each time because
    # patching require_auth must happen before command registration.
    from qa_studio_cli.commands import tests as tests_module
    from qa_studio_cli.api import client as client_module

    original_require_auth = client_module.require_auth

    def fake_require_auth(fn):
        import functools

        @functools.wraps(fn)
        @click.pass_context
        def wrapper(ctx, *args, **kwargs):
            ctx.ensure_object(dict)
            ctx.obj["client"] = mock_client
            return ctx.invoke(fn, *args, **kwargs)

        return wrapper

    # Patch at the module level where require_auth is imported
    with patch.object(client_module, "require_auth", fake_require_auth):
        # Re-import to pick up the patched decorator
        import importlib
        importlib.reload(tests_module)
        cli = click.Group()
        cli.add_command(tests_module.tests)
        result = runner.invoke(cli, ["tests"] + args, input=input_text, catch_exceptions=False)

    # Restore original module
    importlib.reload(tests_module)
    return result


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

usecase_strategy = st.builds(
    UsecaseModel,
    id=st.uuids().map(str),
    name=st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), min_codepoint=32, max_codepoint=126),
    ),
    description=st.text(max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)),
    starting_url=st.from_regex(r"https://[a-z]{1,10}\.[a-z]{2,4}", fullmatch=True),
    active=st.booleans(),
    tags=st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L",))), max_size=3),
    created_at=st.from_regex(r"2024-0[1-9]-[012][0-9]T[01][0-9]:[0-5][0-9]:[0-5][0-9]Z", fullmatch=True),
    executing_region=st.sampled_from(["us-east-1", "eu-west-1", "ap-southeast-1"]),
    model_id=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Pd"))),
)


# ---------------------------------------------------------------------------
# Property test: List output contains all resource identifiers (Property 7)
# Sub-task 5.3
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 7: List output contains all resource identifiers (tests)
# **Validates: Requirements 3.2**
class TestListOutputProperty:
    """For any non-empty list of UsecaseModel instances, CLI output contains every test's name, id, and description."""

    @given(items=st.lists(usecase_strategy, min_size=1, max_size=5))
    @settings(max_examples=100)
    def test_list_output_contains_all_names_and_ids(self, items):
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "usecases": [item.model_dump(by_alias=True) for item in items]
        }

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["list"])

        assert result.exit_code == 0
        for item in items:
            assert item.name in result.output
            assert item.id in result.output
            assert item.description in result.output


# ---------------------------------------------------------------------------
# Property test: Detail output contains all specified fields (Property 8)
# Sub-task 5.4
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 8: Detail output contains all specified fields (tests)
# **Validates: Requirements 4.2**
class TestDetailOutputProperty:
    """For any UsecaseModel with non-empty fields, CLI output of tests get contains all fields."""

    @given(item=usecase_strategy)
    @settings(max_examples=100)
    def test_get_output_contains_all_fields(self, item):
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            item.model_dump(by_alias=True),
            {"steps": []},
        ]

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["get", item.id])

        assert result.exit_code == 0
        assert item.name in result.output
        assert item.description in result.output
        assert item.starting_url in result.output
        assert str(item.active) in result.output
        assert item.executing_region in result.output
        assert item.model_id in result.output
        assert item.created_at in result.output
        # Tags: each tag should appear in output
        for tag in item.tags:
            assert tag in result.output


# ---------------------------------------------------------------------------
# Property test: ApiError propagation to stderr (Property 9)
# Sub-task 5.5
# ---------------------------------------------------------------------------

# Feature: wp4-api-commands, Property 9: ApiError propagation to stderr with exit code 1
# **Validates: Requirements 3.4, 13.3**
class TestApiErrorPropagationProperty:
    """When ApiClient raises ApiError, CLI writes error to stderr and exits with code 1."""

    @given(
        status_code=st.integers(min_value=400, max_value=599),
        message=st.text(min_size=1, max_size=100, alphabet=st.characters(min_codepoint=32, max_codepoint=126)),
    )
    @settings(max_examples=100)
    def test_list_api_error_propagates_to_stderr(self, status_code, message):
        mock_client = MagicMock()
        mock_client.get.side_effect = ApiError(status_code, message)

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["list"])

        assert result.exit_code == 1
        assert message in result.output


# ---------------------------------------------------------------------------
# Unit tests for tests commands (Sub-task 5.6)
# ---------------------------------------------------------------------------

class TestListCommand:
    """Unit tests for tests list command."""

    def test_displays_table_with_names_ids_and_descriptions(self):
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "usecases": [
                {"id": "abc-123", "name": "Login Test", "description": "Test login flow"},
                {"id": "def-456", "name": "Checkout Test", "description": "Test checkout"},
            ]
        }

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["list"])

        assert result.exit_code == 0
        assert "Login Test" in result.output
        assert "abc-123" in result.output
        assert "Test login flow" in result.output
        assert "Checkout Test" in result.output
        assert "def-456" in result.output
        assert "Test checkout" in result.output

    def test_shows_no_tests_found_for_empty_response(self):
        mock_client = MagicMock()
        mock_client.get.return_value = {"usecases": []}

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["list"])

        assert result.exit_code == 0
        assert "No tests found" in result.output

    def test_shows_error_and_exits_1_on_api_failure(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = ApiError(500, "Internal server error")

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["list"])

        assert result.exit_code == 1
        assert "Internal server error" in result.output


class TestGetCommand:
    """Unit tests for tests get command."""

    def test_displays_all_test_fields(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            {
                "id": "abc-123",
                "name": "Login Test",
                "description": "Test the login flow",
                "startingUrl": "https://example.com/login",
                "active": True,
                "executingRegion": "us-east-1",
                "modelId": "anthropic.claude-v2",
                "tags": ["smoke", "auth"],
                "createdAt": "2024-01-15T10:30:00Z",
            },
            {
                "steps": [
                    {"id": "s1", "sort": 1, "instruction": "Navigate to login page", "step_type": "navigation"},
                    {"id": "s2", "sort": 2, "instruction": "Check title is visible", "step_type": "validation"},
                ]
            },
        ]

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["get", "abc-123"])

        assert result.exit_code == 0
        assert "Login Test" in result.output
        assert "Test the login flow" in result.output
        assert "https://example.com/login" in result.output
        assert "True" in result.output
        assert "us-east-1" in result.output
        assert "anthropic.claude-v2" in result.output
        assert "smoke" in result.output
        assert "auth" in result.output
        assert "2024-01-15T10:30:00Z" in result.output
        # Steps
        assert "Steps (2)" in result.output
        assert "Navigate to login page" in result.output
        assert "[navigation]" in result.output
        assert "Check title is visible" in result.output
        assert "[validation]" in result.output

    def test_displays_no_steps_message(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            {"id": "abc-123", "name": "Empty Test", "description": ""},
            {"steps": []},
        ]

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["get", "abc-123"])

        assert result.exit_code == 0
        assert "Steps (0)" in result.output
        assert "No steps defined" in result.output

    def test_shows_not_found_on_404(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = ApiError(404, "Resource not found.")

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["get", "nonexistent-id"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestCreateCommand:
    """Unit tests for tests create --from-journey command."""

    def test_prompts_for_all_inputs_and_calls_generate_import(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = [
            # generate-usecase response
            {"success": True, "usecaseData": '{"steps": []}', "message": ""},
            # import response
            {"success": True, "usecaseId": "new-test-id", "message": ""},
        ]

        runner = CliRunner()
        input_text = "My Test\nhttps://example.com\nNavigate to the login page, click the sign in button, enter username and password, click submit button, verify dashboard is visible\nus-east-1\n"
        result = _invoke_with_mock(runner, mock_client, ["create", "--from-journey"], input_text=input_text)

        assert result.exit_code == 0
        assert "new-test-id" in result.output
        assert "My Test" in result.output

        # Verify both API calls were made
        assert mock_client.post.call_count == 2
        gen_call = mock_client.post.call_args_list[0]
        assert gen_call[0][0] == "/api/generate-usecase"
        assert gen_call[1]["json_body"]["title"] == "My Test"
        assert gen_call[1]["json_body"]["starting_url"] == "https://example.com"
        assert "Navigate to the login page" in gen_call[1]["json_body"]["userJourney"]
        assert gen_call[1]["json_body"]["region"] == "us-east-1"

        import_call = mock_client.post.call_args_list[1]
        assert import_call[0][0] == "/api/import"

    def test_shows_error_on_generation_failure(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {
            "success": False,
            "usecaseData": "",
            "message": "AI generation timed out",
        }

        runner = CliRunner()
        input_text = "My Test\nhttps://example.com\nNavigate to the login page, click the sign in button, enter username and password, click submit button, verify dashboard is visible\nus-east-1\n"
        result = _invoke_with_mock(runner, mock_client, ["create", "--from-journey"], input_text=input_text)

        assert result.exit_code == 1
        assert "Generation failed" in result.output

    def test_shows_error_on_api_error(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ApiError(502, "Bad gateway")

        runner = CliRunner()
        input_text = "My Test\nhttps://example.com\nNavigate to the login page, click the sign in button, enter username and password, click submit button, verify dashboard is visible\nus-east-1\n"
        result = _invoke_with_mock(runner, mock_client, ["create", "--from-journey"], input_text=input_text)

        assert result.exit_code == 1
        assert "Bad gateway" in result.output

    def test_accepts_cli_options(self):
        """Test create accepts CLI options instead of prompts."""
        mock_client = MagicMock()
        mock_client.post.side_effect = [
            {"success": True, "usecaseData": '{"steps": []}', "message": ""},
            {"success": True, "usecaseId": "opt-test-id", "message": ""},
        ]

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            [
                "create",
                "--from-journey",
                "--title", "CLI Options Test",
                "--url", "https://example.com/test",
                "--journey", "Navigate to the login page, click the sign in button, enter username and password, click submit button, verify dashboard is visible",
                "--region", "us-west-2",
            ],
            input_text=""  # No prompts needed
        )

        assert result.exit_code == 0
        assert "opt-test-id" in result.output

        # Verify API call used CLI options
        gen_call = mock_client.post.call_args_list[0]
        assert gen_call[1]["json_body"]["title"] == "CLI Options Test"
        assert gen_call[1]["json_body"]["starting_url"] == "https://example.com/test"
        assert gen_call[1]["json_body"]["region"] == "us-west-2"

    def test_validates_journey_client_side(self):
        """Test client-side validation rejects invalid journey."""
        mock_client = MagicMock()

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            [
                "create",
                "--from-journey",
                "--title", "Test",
                "--url", "https://example.com",
                "--journey", "Too short",  # Invalid: too short, no action words
                "--region", "us-east-1",
            ],
            input_text=""
        )

        assert result.exit_code == 1
        assert "Validation failed" in result.output
        # Should not make API call
        assert mock_client.post.call_count == 0

    def test_validates_url_client_side(self):
        """Test client-side validation rejects invalid URL."""
        mock_client = MagicMock()

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            [
                "create",
                "--from-journey",
                "--title", "Test",
                "--url", "not-a-url",  # Invalid URL
                "--journey", "Navigate to the login page, click the sign in button, enter username and password, click submit button, verify dashboard is visible",
                "--region", "us-east-1",
            ],
            input_text=""
        )

        assert result.exit_code == 1
        assert "Validation failed" in result.output
        assert mock_client.post.call_count == 0


class TestDeleteCommand:
    """Unit tests for tests delete command."""

    def test_prompts_for_confirmation(self):
        mock_client = MagicMock()
        mock_client.delete.return_value = None

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["delete", "abc-123"], input_text="y\n")

        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
        mock_client.delete.assert_called_once_with("/api/usecase/abc-123")

    def test_aborts_on_no_confirmation(self):
        mock_client = MagicMock()

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["delete", "abc-123"], input_text="n\n")

        assert result.exit_code == 0
        assert "Aborted" in result.output
        mock_client.delete.assert_not_called()

    def test_yes_flag_skips_confirmation(self):
        mock_client = MagicMock()
        mock_client.delete.return_value = None

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["delete", "abc-123", "--yes"])

        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
        mock_client.delete.assert_called_once_with("/api/usecase/abc-123")

    def test_shows_not_found_on_404(self):
        mock_client = MagicMock()
        mock_client.delete.side_effect = ApiError(404, "Resource not found.")

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["delete", "abc-123", "--yes"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# Property test: Run command output contains execution details (Property)
# ---------------------------------------------------------------------------

class TestRunOutputProperty:
    """For any ExecuteUsecaseResponse, CLI output contains execution_id and status."""

    @given(
        usecase_id=st.uuids().map(str),
        execution_id=st.uuids().map(str),
        status=st.sampled_from(["task started", "usecase queued", "execution created"]),
        task_id=st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Pd"))),
    )
    @settings(max_examples=100)
    def test_run_output_contains_execution_details(self, usecase_id, execution_id, status, task_id):
        mock_client = MagicMock()
        response = {
            "status": status,
            "usecaseId": usecase_id,
            "executionId": execution_id,
            "taskArn": "",
            "taskId": task_id,
            "cloudWatchLogsUrl": "",
        }
        mock_client.post.return_value = response

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["run", usecase_id])

        assert result.exit_code == 0
        assert execution_id in result.output
        assert status in result.output
        assert usecase_id in result.output


# ---------------------------------------------------------------------------
# Unit tests for tests run command
# ---------------------------------------------------------------------------

class TestRunCommand:
    """Unit tests for tests run command."""

    def test_executes_test_with_default_trigger_type(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {
            "status": "task started",
            "usecaseId": "abc-123",
            "executionId": "exec-456",
            "taskArn": "arn:aws:ecs:us-east-1:123:task/cluster/task-id",
            "taskId": "task-id",
            "cloudWatchLogsUrl": "https://console.aws.amazon.com/cloudwatch/logs",
        }

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["run", "abc-123"])

        assert result.exit_code == 0
        assert "exec-456" in result.output
        assert "task started" in result.output
        assert "abc-123" in result.output
        assert "task-id" in result.output
        assert "cloudwatch" in result.output.lower()

        # Verify API call uses query params with default trigger type
        mock_client.post.assert_called_once_with(
            "/api/usecase/abc-123/execute",
            params={"trigger-type": "OnDemandHeadless"},
        )

    def test_executes_test_with_on_demand_trigger(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {
            "status": "usecase queued",
            "usecaseId": "abc-123",
        }

        runner = CliRunner()
        result = _invoke_with_mock(
            runner, mock_client, ["run", "abc-123", "--trigger-type", "OnDemand"]
        )

        assert result.exit_code == 0
        assert "usecase queued" in result.output
        mock_client.post.assert_called_once_with(
            "/api/usecase/abc-123/execute",
            params={"trigger-type": "OnDemand"},
        )

    def test_executes_test_with_ci_runner_trigger(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {
            "status": "execution created",
            "usecaseId": "abc-123",
            "executionId": "exec-789",
        }

        runner = CliRunner()
        result = _invoke_with_mock(
            runner, mock_client, ["run", "abc-123", "--trigger-type", "ci_runner"]
        )

        assert result.exit_code == 0
        assert "execution created" in result.output
        assert "exec-789" in result.output
        mock_client.post.assert_called_once_with(
            "/api/usecase/abc-123/execute",
            params={"trigger-type": "ci_runner"},
        )

    def test_hides_task_id_when_empty(self):
        mock_client = MagicMock()
        mock_client.post.return_value = {
            "status": "usecase queued",
            "usecaseId": "abc-123",
        }

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["run", "abc-123", "--trigger-type", "OnDemand"])

        assert result.exit_code == 0
        assert "Task ID" not in result.output
        assert "Logs" not in result.output

    def test_shows_error_on_404(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ApiError(404, "Resource not found.")

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["run", "nonexistent-id"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_shows_error_on_api_failure(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = ApiError(500, "Failed to execute usecase")

        runner = CliRunner()
        result = _invoke_with_mock(runner, mock_client, ["run", "abc-123"])

        assert result.exit_code == 1
        assert "Failed to execute usecase" in result.output

    def test_accepts_cli_options(self):
        """Test create accepts CLI options instead of prompts."""
        mock_client = MagicMock()
        mock_client.post.side_effect = [
            {"success": True, "usecaseData": '{"steps": []}', "message": ""},
            {"success": True, "usecaseId": "opt-test-id", "message": ""},
        ]

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            [
                "create",
                "--from-journey",
                "--title", "CLI Options Test",
                "--url", "https://example.com/test",
                "--journey", "Navigate to the login page, click the sign in button, enter username and password, click submit button, verify dashboard is visible",
                "--region", "us-west-2",
            ],
            input_text=""  # No prompts needed
        )

        assert result.exit_code == 0
        assert "opt-test-id" in result.output

        # Verify API call used CLI options
        gen_call = mock_client.post.call_args_list[0]
        assert gen_call[1]["json_body"]["title"] == "CLI Options Test"
        assert gen_call[1]["json_body"]["starting_url"] == "https://example.com/test"
        assert gen_call[1]["json_body"]["region"] == "us-west-2"

    def test_validates_journey_client_side(self):
        """Test client-side validation rejects invalid journey."""
        mock_client = MagicMock()

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            [
                "create",
                "--from-journey",
                "--title", "Test",
                "--url", "https://example.com",
                "--journey", "Too short",  # Invalid: too short, no action words
                "--region", "us-east-1",
            ],
            input_text=""
        )

        assert result.exit_code == 1
        assert "Validation failed" in result.output
        # Should not make API call
        assert mock_client.post.call_count == 0

    def test_validates_url_client_side(self):
        """Test client-side validation rejects invalid URL."""
        mock_client = MagicMock()

        runner = CliRunner()
        result = _invoke_with_mock(
            runner,
            mock_client,
            [
                "create",
                "--from-journey",
                "--title", "Test",
                "--url", "not-a-url",  # Invalid URL
                "--journey", "Navigate to the login page, click the sign in button, enter username and password, click submit button, verify dashboard is visible",
                "--region", "us-east-1",
            ],
            input_text=""
        )

        assert result.exit_code == 1
        assert "Validation failed" in result.output
        assert mock_client.post.call_count == 0
