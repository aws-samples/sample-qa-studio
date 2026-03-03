"""Click command group for test suite management."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.models.api import SuiteExecutionResponse, SuiteModel, SuiteUsecaseModel
from qa_studio_cli.models.errors import ApiError


@click.group()
def suites():
    """Manage test suites."""
    pass


@suites.command("list")
@require_auth
@click.pass_context
def list_suites(ctx):
    """List all test suites."""
    client = ctx.obj["client"]
    try:
        data = client.get("/api/test-suites")
        raw_items = data.get("suites", [])
        items = [SuiteModel.model_validate(item) for item in raw_items]

        if not items:
            click.echo("No suites found.")
            return

        click.echo(f"{'ID':<40} {'Tests':>5}  {'Name'}")
        click.echo(f"{'─' * 40} {'─' * 5}  {'─' * 30}")
        for item in items:
            click.echo(f"{item.id:<40} {item.total_usecases:>5}  {item.name}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@suites.command("get")
@require_auth
@click.argument("id")
@click.pass_context
def get_suite(ctx, id):
    """Get suite details."""
    client = ctx.obj["client"]
    try:
        data = client.get(f"/api/test-suites/{id}")
        item = SuiteModel.model_validate(data)

        click.echo(f"Name:           {item.name}")
        click.echo(f"Description:    {item.description}")
        click.echo(f"Tags:           {', '.join(item.tags) if item.tags else '—'}")
        click.echo(f"Total Usecases: {item.total_usecases}")
        click.echo(f"Created By:     {item.created_by}")
        click.echo(f"Created At:     {item.created_at}")

        # Fetch and display usecases in the suite
        uc_data = client.get(f"/api/test-suites/{id}/usecases")
        raw_usecases = uc_data.get("usecases", [])
        usecases = [SuiteUsecaseModel.model_validate(uc) for uc in raw_usecases]

        click.echo(f"\nUsecases ({len(usecases)}):")
        if not usecases:
            click.echo("  No usecases in this suite.")
        else:
            for uc in usecases:
                click.echo(f"  {uc.usecase_id}  {uc.usecase_name}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@suites.command("create")
@require_auth
@click.option("--name", required=True, help="Suite name")
@click.option("--description", required=True, help="Suite description")
@click.option("--tags", multiple=True, help="Tags (repeatable)")
@click.pass_context
def create_suite(ctx, name, description, tags):
    """Create a new test suite."""
    if not name or not name.strip():
        click.echo("Error: Suite name cannot be empty or whitespace.", err=True)
        raise SystemExit(1)

    client = ctx.obj["client"]
    try:
        body = {"name": name, "description": description}
        if tags:
            body["tags"] = list(tags)

        data = client.post("/api/test-suites", json_body=body)
        click.echo(f"✓ Suite created: {data.get('name', name)} (ID: {data['id']})")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@suites.command("add-tests")
@require_auth
@click.argument("suite_id")
@click.argument("usecase_ids", nargs=-1, required=True)
@click.pass_context
def add_tests(ctx, suite_id, usecase_ids):
    """Add tests to a suite."""
    client = ctx.obj["client"]
    try:
        data = client.post(
            f"/api/test-suites/{suite_id}/usecases",
            json_body={"usecaseIds": list(usecase_ids)},
        )
        added = data.get("added", 0)
        total = data.get("totalUsecases", 0)
        click.echo(f"✓ Added {added} test(s). Total usecases in suite: {total}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@suites.command("remove-test")
@require_auth
@click.argument("suite_id")
@click.argument("usecase_id")
@click.pass_context
def remove_test(ctx, suite_id, usecase_id):
    """Remove a test from a suite."""
    client = ctx.obj["client"]
    try:
        client.delete(f"/api/test-suites/{suite_id}/usecases/{usecase_id}")
        click.echo(f"✓ Removed test {usecase_id} from suite {suite_id}.")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@suites.command("run")
@require_auth
@click.argument("suite_id")
@click.option("--base-url", default=None, help="Base URL override")
@click.option("--var", "variables", multiple=True, help="Variable override KEY=VALUE (repeatable)")
@click.option("--region", default=None, help="AWS region override")
@click.option("--model-id", default=None, help="Bedrock model ID override")
@click.pass_context
def run_suite(ctx, suite_id, base_url, variables, region, model_id):
    """Execute a test suite via the API."""
    client = ctx.obj["client"]

    body = {"trigger_type": "ci_runner"}

    overrides = {}
    if base_url:
        overrides["base_url"] = base_url
    if region:
        overrides["region"] = region
    if model_id:
        overrides["model_id"] = model_id
    if variables:
        parsed_vars = {}
        for var in variables:
            key, _, value = var.partition("=")
            parsed_vars[key] = value
        overrides["variables"] = parsed_vars

    if overrides:
        body["overrides"] = overrides

    try:
        data = client.post(f"/api/test-suites/{suite_id}/execute", json_body=body)
        result = SuiteExecutionResponse.model_validate(data)
        exec_count = len(result.execution_ids)
        click.echo(f"✓ Suite execution started: {result.suite_execution_id}")
        click.echo(f"  Executions created: {exec_count}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
