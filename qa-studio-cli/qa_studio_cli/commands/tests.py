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
@click.option("--title", help="Test name")
@click.option("--url", help="Starting URL")
@click.option("--journey", help="User journey description")
@click.option("--region", type=click.Choice(['us-east-1', 'us-west-2', 'ap-southeast-2', 'eu-central-1']), help="AWS region for execution (default: us-east-1)")
@click.pass_context
def create_test(ctx, from_journey, title, url, journey, region):
    """Create a test from a user journey description."""
    from qa_studio_cli.validation import (
        validate_title, validate_url, validate_journey_description, validate_region
    )
    
    client = ctx.obj["client"]

    # Get inputs from options or prompts
    title = title or click.prompt("Title")
    starting_url = url or click.prompt("Starting URL")
    user_journey = journey or click.prompt("User journey description")
    region = region or click.prompt("Region", default="us-east-1", type=click.Choice(['us-east-1', 'us-west-2', 'ap-southeast-2', 'eu-central-1']))

    # Client-side validation
    validation_errors = []
    
    is_valid, errors = validate_title(title)
    if not is_valid:
        validation_errors.extend([f"Title: {e}" for e in errors])
    
    is_valid, errors = validate_url(starting_url)
    if not is_valid:
        validation_errors.extend([f"URL: {e}" for e in errors])
    
    is_valid, errors = validate_journey_description(user_journey)
    if not is_valid:
        validation_errors.extend([f"Journey: {e}" for e in errors])
    
    is_valid, errors = validate_region(region)
    if not is_valid:
        validation_errors.extend([f"Region: {e}" for e in errors])
    
    if validation_errors:
        click.echo("Validation failed:", err=True)
        for error in validation_errors:
            click.echo(f"  • {error}", err=True)
        raise SystemExit(1)

    try:
        # Step 1: Generate usecase from journey
        gen_data = client.post("/api/generate-usecase", json_body={
            "title": title,
            "starting_url": starting_url,
            "user_journey": user_journey,
            "region": region,
        })
        gen_response = GenerateUsecaseResponse.model_validate(gen_data)

        if not gen_response.success:
            click.echo(f"Generation failed: {gen_response.message}", err=True)
            raise SystemExit(1)

        # Step 2: Import the generated usecase
        # Parse the usecaseData JSON string into a dict
        import json as json_module
        try:
            usecase_data_dict = json_module.loads(gen_response.usecase_data)
        except json_module.JSONDecodeError as e:
            click.echo(f"Failed to parse generated usecase data: {e}", err=True)
            raise SystemExit(1)
        
        # Send the parsed data directly to import endpoint
        import_data = client.post("/api/import", json_body=usecase_data_dict)
        import_response = ImportUsecaseResponse.model_validate(import_data)

        if not import_response.success:
            click.echo(f"Import failed: {import_response.message}", err=True)
            raise SystemExit(1)

        click.echo(f"✓ Test created: {title} (ID: {import_response.usecase_id})")

    except ApiError as e:
        # Try to parse validation errors from API response
        error_str = str(e)
        if "validation" in error_str.lower() and hasattr(e, 'response_data'):
            details = e.response_data.get('details', {})
            validation_errors = details.get('validationErrors', [])
            if validation_errors:
                click.echo("API validation failed:", err=True)
                for err in validation_errors:
                    field = err.get('field', 'unknown')
                    message = err.get('message', 'Unknown error')
                    click.echo(f"  • {field}: {message}", err=True)
            else:
                click.echo(error_str, err=True)
        else:
            click.echo(error_str, err=True)
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

