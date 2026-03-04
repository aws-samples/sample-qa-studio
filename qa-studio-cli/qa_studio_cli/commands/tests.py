"""Click command group for test (usecase) management."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.models.api import (
    ExecuteUsecaseResponse,
    GenerateUsecaseResponse,
    ImportUsecaseResponse,
    StepModel,
    UsecaseModel,
)
from qa_studio_cli.models.errors import ApiError


@click.group()
def tests():
    """Manage tests (usecases)."""
    pass


@tests.command("list")
@require_auth
@click.pass_context
def list_tests(ctx):
    """List all tests."""
    client = ctx.obj["client"]
    try:
        data = client.get("/api/usecases")
        raw_items = data.get("usecases", [])
        items = [UsecaseModel.model_validate(item) for item in raw_items]

        if not items:
            click.echo("No tests found.")
            return

        for i, item in enumerate(items):
            if i > 0:
                click.echo()
            click.echo(f"ID:          {item.id}")
            click.echo(f"Name:        {item.name}")
            click.echo(f"Description: {item.description}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@tests.command("get")
@require_auth
@click.argument("id")
@click.pass_context
def get_test(ctx, id):
    """Get test details including steps."""
    client = ctx.obj["client"]
    try:
        data = client.get(f"/api/usecase/{id}")
        item = UsecaseModel.model_validate(data)

        click.echo(f"Name:         {item.name}")
        click.echo(f"Description:  {item.description}")
        click.echo(f"Starting URL: {item.starting_url}")
        click.echo(f"Active:       {item.active}")
        click.echo(f"Region:       {item.executing_region}")
        click.echo(f"Model:        {item.model_id}")
        click.echo(f"Tags:         {', '.join(item.tags) if item.tags else '—'}")
        click.echo(f"Created At:   {item.created_at}")

        # Fetch and display steps
        steps_data = client.get(f"/api/usecase/{id}/steps")
        raw_steps = steps_data.get("steps", [])
        steps = [StepModel.model_validate(s) for s in raw_steps]
        steps.sort(key=lambda s: s.sort)

        click.echo(f"\nSteps ({len(steps)}):")
        if not steps:
            click.echo("  No steps defined.")
        else:
            for step in steps:
                click.echo(f"  {step.sort:>3}. [{step.step_type}] {step.instruction}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@tests.command("create")
@require_auth
@click.option("--from-journey", is_flag=True, required=True, help="Create from user journey description")
@click.option("--title", prompt=True, help="Title for the test case")
@click.option("--url", "starting_url", prompt="Starting URL", help="Starting URL for the test")
@click.option("--journey", "user_journey", prompt="User journey description", help="Description of the user journey")
@click.option("--region", prompt=True, help="AWS region for execution (e.g. us-east-1, eu-central-1)")
@click.option("--export-to", "export_to", default=None, help="Directory to export generated JSON to")
@click.pass_context
def create_test(ctx, from_journey, title, starting_url, user_journey, region, export_to):
    """Create a test from a user journey description."""
    client = ctx.obj["client"]

    try:
        # Step 1: Generate usecase from journey
        gen_data = client.post("/api/generate-usecase", json_body={
            "title": title,
            "startingUrl": starting_url,
            "userJourney": user_journey,
            "region": region,
        })
        gen_response = GenerateUsecaseResponse.model_validate(gen_data)

        if not gen_response.success:
            click.echo(f"Generation failed: {gen_response.message}", err=True)
            raise SystemExit(1)

        # Step 2: Import the generated usecase
        import_data = client.post("/api/import", json_body={
            "usecaseData": gen_response.usecase_data,
            "name": title,
        })
        import_response = ImportUsecaseResponse.model_validate(import_data)

        if not import_response.success:
            click.echo(f"Import failed: {import_response.message}", err=True)
            raise SystemExit(1)

        click.echo(f"✓ Test created: {title} (ID: {import_response.usecase_id})")

        # Step 3: Export JSON if --export-to is provided
        if export_to:
            import os
            os.makedirs(export_to, exist_ok=True)
            safe_title = title.replace(" ", "_")
            safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in safe_title)
            filepath = os.path.join(export_to, f"{safe_title}.json")
            with open(filepath, "w") as f:
                f.write(gen_response.usecase_data)
            click.echo(f"Test JSON exported to: {filepath}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@tests.command("delete")
@require_auth
@click.argument("id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_test(ctx, id, yes):
    """Delete a test."""
    client = ctx.obj["client"]

    if not yes:
        if not click.confirm(f"Delete test {id}?"):
            click.echo("Aborted.")
            return

    try:
        client.delete(f"/api/usecase/{id}")
        click.echo(f"✓ Test {id} deleted.")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

@tests.command("run")
@require_auth
@click.argument("id")
@click.option(
    "--trigger-type",
    type=click.Choice(["OnDemandHeadless", "OnDemand", "ci_runner"], case_sensitive=True),
    default="OnDemandHeadless",
    help="Execution trigger type (default: OnDemandHeadless)",
)
@click.pass_context
def run_test(ctx, id, trigger_type):
    """Execute a single test."""
    client = ctx.obj["client"]
    try:
        data = client.post(
            f"/api/usecase/{id}/execute",
            params={"trigger-type": trigger_type},
        )
        result = ExecuteUsecaseResponse.model_validate(data)

        click.echo(f"✓ Execution started: {result.execution_id}")
        click.echo(f"  Status:  {result.status}")
        click.echo(f"  Test ID: {result.usecase_id}")
        if result.task_id:
            click.echo(f"  Task ID: {result.task_id}")
        if result.cloud_watch_logs_url:
            click.echo(f"  Logs:    {result.cloud_watch_logs_url}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

