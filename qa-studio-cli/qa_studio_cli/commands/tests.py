"""Click command group for test (usecase) management."""

import json
from pathlib import Path

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.api.usecases import UseCaseAPI
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
        raw_items = UseCaseAPI(client).list_usecases()
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
        data = client.get(f"/usecase/{id}")
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
        steps_data = client.get(f"/usecase/{id}/steps")
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
        gen_data = client.post("/generate-usecase", json_body={
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
        usecase_data = json.loads(gen_response.usecase_data)
        import_data = client.post("/import", json_body=usecase_data)
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
        client.delete(f"/usecase/{id}")
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
            f"/usecase/{id}/execute",
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



@tests.command("import")
@require_auth
@click.argument("path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Validate only, do not import")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option(
    "--non-interactive", is_flag=True,
    help=(
        "Run without any prompts. Implies -y. Fails with exit code 2 if any "
        "secret value is missing — supply via --secret KEY=VALUE, or use "
        "--skip-secrets to defer setting."
    ),
)
@click.option(
    "--secret", "secret_args", multiple=True, metavar="KEY=VALUE",
    help=(
        "Pre-supply a secret value (repeatable). Suppresses the interactive "
        "prompt for that key. Errors if KEY is not declared by any imported test."
    ),
)
@click.option("--base-url", default=None, help="Override starting_url for all imports")
@click.option("--region", default=None, help="Override executing_region for all imports")
@click.option("--skip-secrets", is_flag=True, help="Skip interactive secret prompts")
@click.option(
    "--format", "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human", help="Output format (default: human)",
)
@click.pass_context
def import_tests(
    ctx, path, dry_run, yes, non_interactive, secret_args, base_url, region,
    skip_secrets, output_format,
):
    """Import test cases from a JSON file or folder."""
    from qa_studio_cli.importers.scanner import scan_all
    from qa_studio_cli.importers.executor import execute_imports, set_secret_value

    client = ctx.obj["client"]
    is_json = output_format == "json"

    # Parse --secret KEY=VALUE args up front (raises click.BadParameter on malformed)
    cli_secrets = _parse_cli_secrets(secret_args)

    # Phase 1: Scan & Validate
    results = scan_all(Path(path))

    if not results:
        if is_json:
            click.echo(json.dumps({"error": "No JSON files found"}))
        else:
            click.echo("No JSON files found.", err=True)
        raise SystemExit(1)

    valid = [r for r in results if r.is_valid]
    invalid = [r for r in results if not r.is_valid]

    # Display validation summary
    if is_json:
        json_output = _build_validation_json(results)
    else:
        _print_validation_table(results)

    # Dry-run: stop here
    if dry_run:
        if is_json:
            click.echo(json.dumps(json_output, indent=2))
        exit_code = 0 if valid else 1
        raise SystemExit(exit_code)

    # All invalid: stop
    if not valid:
        if is_json:
            click.echo(json.dumps(json_output, indent=2))
        else:
            click.echo("\nNo valid files to import.", err=True)
        raise SystemExit(1)

    # Build the set of unique secret keys referenced across all valid files
    unique_secret_keys: set[str] = set()
    for scan_result in valid:
        for s in scan_result.payload.secrets:
            unique_secret_keys.add(s.key)

    # Hard error: --secret references a key that no imported test declares
    unknown_keys = sorted(set(cli_secrets) - unique_secret_keys)
    if unknown_keys:
        available = ", ".join(sorted(unique_secret_keys)) or "(none)"
        msg = (
            f"--secret references unknown key(s): {', '.join(unknown_keys)}. "
            f"Available secret key(s): {available}."
        )
        if is_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        raise SystemExit(2)

    # --non-interactive implies --yes for the import confirmation
    effective_yes = yes or non_interactive

    # Confirmation
    if not is_json and not effective_yes:
        if not click.confirm(f"\nImport {len(valid)} test(s)?"):
            click.echo("Aborted.")
            raise SystemExit(0)

    # Determine which declared secrets are not yet supplied via --secret
    unsupplied_keys = sorted(unique_secret_keys - set(cli_secrets))

    # Hard error: non-interactive mode with missing values and no --skip-secrets
    if non_interactive and unsupplied_keys and not skip_secrets:
        msg = (
            f"--non-interactive set but missing secret values for: "
            f"{', '.join(unsupplied_keys)}. "
            f"Provide via --secret KEY=VALUE, or use --skip-secrets to defer setting."
        )
        if is_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(f"Error: {msg}", err=True)
        raise SystemExit(2)

    # Build prompted_values: start with --secret args, prompt for the rest if interactive
    prompted_values: dict[str, str] = dict(cli_secrets)
    should_prompt_secrets = (
        not skip_secrets
        and not is_json
        and not non_interactive
        and bool(unsupplied_keys)
    )

    if should_prompt_secrets:
        # Build description map for unsupplied keys (first-seen description wins)
        unsupplied_descriptions: dict[str, str] = {}
        for scan_result in valid:
            for s in scan_result.payload.secrets:
                if s.key in unsupplied_keys and s.key not in unsupplied_descriptions:
                    unsupplied_descriptions[s.key] = s.description

        click.echo("\nSecrets (shared across all imported tests):")
        for key in unsupplied_keys:
            description = unsupplied_descriptions.get(key, "")
            desc = f" ({description})" if description else ""
            value = click.prompt(
                f"  {key}{desc}",
                hide_input=True,
                default="",
                show_default=False,
            )
            if value:
                prompted_values[key] = value

    # Distribute supplied values to each file that needs them
    secret_values: dict[str, dict[str, str]] = {}
    if prompted_values:
        for scan_result in valid:
            file_secrets = {
                s.key: prompted_values[s.key]
                for s in scan_result.payload.secrets
                if s.key in prompted_values
            }
            if file_secrets:
                secret_values[scan_result.file_name] = file_secrets

    # Phase 2: Import
    import_results = execute_imports(
        client, valid, base_url=base_url, region=region, secret_values=secret_values or None,
    )

    # Display results
    if is_json:
        json_output["import"] = _build_import_json(import_results)
        click.echo(json.dumps(json_output, indent=2))
    else:
        _print_import_table(import_results)

        # Report skipped secrets
        if skip_secrets:
            all_missing = []
            for r in import_results:
                if r.success and r.missing_secrets:
                    all_missing.extend(r.missing_secrets)
            if all_missing:
                click.echo(
                    f"\n⚠ Skipped secrets (configure in UI): "
                    f"{', '.join(all_missing)}"
                )

    # Exit code
    has_failures = any(not r.success for r in import_results)
    raise SystemExit(1 if has_failures else 0)


def _print_validation_table(results):
    """Print human-readable validation summary table."""
    click.echo(f"\nScanned {len(results)} file(s):\n")

    # Calculate dynamic column widths
    fw = max((len(r.file_name) for r in results), default=4)
    nw = max(
        (len(r.usecase_name) for r in results if r.is_valid),
        default=12,
    )
    fw = max(fw, 4)   # min "File"
    nw = max(nw, 12)  # min "Usecase Name"

    header = f"{'File':<{fw}}  {'Usecase Name':<{nw}}  {'Steps':>5}  {'Secrets':>7}  Status"
    click.echo(header)
    click.echo("─" * len(header))

    for r in results:
        if r.is_valid:
            click.echo(
                f"{r.file_name:<{fw}}  {r.usecase_name:<{nw}}  "
                f"{r.step_count:>5}  {r.secrets_count:>7}  ✓ Valid"
            )
        else:
            errs = "; ".join(r.errors[:2])
            click.echo(
                f"{r.file_name:<{fw}}  {'—':<{nw}}  {'—':>5}  "
                f"{'—':>7}  ✗ Invalid: {errs}"
            )


def _print_import_table(results):
    """Print human-readable import results table."""
    click.echo(f"\nImport Results:\n")

    fw = max((len(r.file_name) for r in results), default=4)
    fw = max(fw, 4)
    uid_w = 36  # UUID length

    header = f"{'File':<{fw}}  {'Usecase ID':<{uid_w}}  Status"
    click.echo(header)
    click.echo("─" * len(header))

    for r in results:
        if r.success:
            click.echo(
                f"{r.file_name:<{fw}}  {r.usecase_id:<{uid_w}}  ✓ Imported"
            )
        else:
            click.echo(
                f"{r.file_name:<{fw}}  {'—':<{uid_w}}  ✗ Failed: {r.error_message}"
            )


def _build_validation_json(results):
    """Build JSON output for validation phase."""
    valid_count = sum(1 for r in results if r.is_valid)
    return {
        "validation": {
            "total": len(results),
            "valid": valid_count,
            "invalid": len(results) - valid_count,
            "files": [
                {
                    "file": r.file_name,
                    "usecaseName": r.usecase_name,
                    "stepCount": r.step_count,
                    "secretsCount": r.secrets_count,
                    "valid": r.is_valid,
                    "errors": r.errors,
                }
                for r in results
            ],
        }
    }


def _build_import_json(import_results):
    """Build JSON output for import phase."""
    succeeded = sum(1 for r in import_results if r.success)
    return {
        "total": len(import_results),
        "succeeded": succeeded,
        "failed": len(import_results) - succeeded,
        "results": [
            {
                "file": r.file_name,
                "success": r.success,
                "usecaseId": r.usecase_id,
                "missingSecrets": r.missing_secrets,
                "error": r.error_message,
            }
            for r in import_results
        ],
    }



def _parse_cli_secrets(secret_args: tuple[str, ...]) -> dict[str, str]:
    """Parse --secret KEY=VALUE arguments into a dict.

    Rejects malformed arguments (missing '='), empty keys, empty values, and
    duplicate keys. Raises click.BadParameter so Click handles the error and
    exits with code 2.
    """
    result: dict[str, str] = {}
    for arg in secret_args:
        if "=" not in arg:
            raise click.BadParameter(
                f"--secret must be in KEY=VALUE form, got: {arg!r}"
            )
        key, _, value = arg.partition("=")
        key = key.strip()
        if not key:
            raise click.BadParameter(
                f"--secret has empty key: {arg!r}"
            )
        if not value:
            raise click.BadParameter(
                f"--secret value for '{key}' is empty. "
                f"Use --skip-secrets to defer setting a key."
            )
        if key in result:
            raise click.BadParameter(
                f"--secret '{key}' supplied more than once"
            )
        result[key] = value
    return result
