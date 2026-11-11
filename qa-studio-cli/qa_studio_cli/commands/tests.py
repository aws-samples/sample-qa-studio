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
@click.option("--application-id", "application_id", required=True,
              help="Application the test is created in (requires edit access on it)")
@click.option("--export-to", "export_to", default=None, help="Directory to export generated JSON to")
@click.pass_context
def create_test(ctx, from_journey, title, starting_url, user_journey, region, application_id, export_to):
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
        import_data = client.post("/import", json_body={**usecase_data, "application_id": application_id})
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
    type=click.Choice(["OnDemandHeadless", "ci_runner"], case_sensitive=True),
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
@click.option(
    "--application-id", "application_id", default=None,
    help="Application the tests are imported into (required unless --dry-run; needs edit access)",
)
@click.option("--skip-secrets", is_flag=True, help="Skip interactive secret prompts")
@click.option(
    "--format", "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human", help="Output format (default: human)",
)
@click.pass_context
def import_tests(
    ctx, path, dry_run, yes, non_interactive, secret_args, base_url, region,
    application_id, skip_secrets, output_format,
):
    """Import test cases from a JSON file or folder."""
    from qa_studio_cli.importers.scanner import scan_all
    from qa_studio_cli.importers.executor import execute_imports
    from qa_studio_cli.importers.template_resolver import resolve_templates

    client = ctx.obj["client"]
    is_json = output_format == "json"

    # Parse --secret KEY=VALUE args up front (raises click.BadParameter on malformed)
    cli_secrets = _parse_cli_secrets(secret_args)

    # Every use case belongs to an application; the API rejects imports without one
    if not dry_run and not application_id:
        raise click.UsageError("--application-id is required (omit only with --dry-run)")

    # Phase 1: Scan & Validate
    results = scan_all(Path(path))

    if not results:
        if is_json:
            click.echo(json.dumps({"error": "No JSON files found"}))
        else:
            click.echo("No JSON files found.", err=True)
        raise SystemExit(1)

    # Template placeholders: every referenced template must exist (one fetch
    # per distinct id; no call for files without placeholders).  The server
    # expands them — the CLI only learns their names and secret keys.
    resolve_templates(client, results)

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
    # (the file's own ``secrets`` plus the secrets of referenced templates)
    unique_secret_keys: set[str] = set()
    for scan_result in valid:
        unique_secret_keys.update(scan_result.secret_keys())

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
            for key in scan_result.secret_keys():
                if key in unsupplied_keys and not unsupplied_descriptions.get(key):
                    unsupplied_descriptions[key] = scan_result.secret_description(key)

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
                key: prompted_values[key]
                for key in scan_result.secret_keys()
                if key in prompted_values
            }
            if file_secrets:
                secret_values[scan_result.file_name] = file_secrets

    # Phase 2: Import
    import_results = execute_imports(
        client, valid, base_url=base_url, region=region, secret_values=secret_values or None,
        application_id=application_id,
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

    # Exit code: 0 only if every scanned file was imported.  Invalid files
    # were skipped above, so they count as failures too (README: "0 — every
    # file imported successfully").
    has_failures = bool(invalid) or any(not r.success for r in import_results)
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
            templates = ""
            if r.templates:
                templates = "  (templates: " + ", ".join(t["name"] or t["id"] for t in r.templates) + ")"
            click.echo(
                f"{r.file_name:<{fw}}  {r.usecase_name:<{nw}}  "
                f"{r.step_count:>5}  {r.secrets_count:>7}  ✓ Valid{templates}"
            )
        else:
            errs = "; ".join(r.errors[:2])
            click.echo(
                f"{r.file_name:<{fw}}  {'—':<{nw}}  {'—':>5}  "
                f"{'—':>7}  ✗ Invalid: {errs}"
            )

    secret_keys: list[str] = []
    for r in results:
        if r.is_valid:
            secret_keys.extend(k for k in r.secret_keys() if k not in secret_keys)
    if secret_keys:
        click.echo(f"\nRequired secrets: {', '.join(secret_keys)}")


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
                    "secretKeys": r.secret_keys(),
                    "templates": r.templates,
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



@tests.command("insert-template")
@require_auth
@click.argument("usecase_id")
@click.option("--template-id", "template_id", required=True, metavar="UUID", help="Template to insert")
@click.option(
    "--position", type=click.IntRange(min=1), default=None,
    help="The template's first step becomes step N (default: append)",
)
@click.option(
    "--secret", "secret_args", multiple=True, metavar="KEY=VALUE",
    help="Set a template secret value after the insert (repeatable). Unknown keys are rejected.",
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human", help="Output format (default: human)",
)
@click.pass_context
def insert_template(ctx, usecase_id, template_id, position, secret_args, output_format):
    """Insert a template's steps into an existing test at a position."""
    from qa_studio_cli.api.templates import TemplateAPI
    from qa_studio_cli.commands.templates import secret_keys_of_steps
    from qa_studio_cli.importers.executor import set_secret_value
    from qa_studio_cli.models.api import InsertTemplateResponse, TemplateStepModel

    client = ctx.obj["client"]
    api = TemplateAPI(client)
    is_json = output_format == "json"
    cli_secrets = _parse_cli_secrets(secret_args)

    def fail(message: str, exit_code: int) -> None:
        if is_json:
            click.echo(json.dumps({"error": message}))
        else:
            click.echo(f"Error: {message}", err=True)
        raise SystemExit(exit_code)

    try:
        steps = [TemplateStepModel.model_validate(s) for s in api.list_steps(template_id)]
    except ApiError as e:
        fail(str(e), 1)

    template_secret_keys = secret_keys_of_steps(steps)
    unknown_keys = sorted(set(cli_secrets) - set(template_secret_keys))
    if unknown_keys:
        available = ", ".join(template_secret_keys) or "(none)"
        fail(
            f"--secret references key(s) not used by template {template_id}: {', '.join(unknown_keys)}. "
            f"Template secret key(s): {available}.",
            2,
        )

    try:
        response = InsertTemplateResponse.model_validate(api.insert_into_usecase(usecase_id, template_id, position))
    except ApiError as e:
        fail(str(e), 1)

    secrets_set: list[str] = []
    secrets_failed: list[str] = []
    for key in template_secret_keys:
        if key not in cli_secrets:
            continue
        (secrets_set if set_secret_value(client, usecase_id, key, cli_secrets[key]) else secrets_failed).append(key)
    missing_secrets = [k for k in template_secret_keys if k not in secrets_set]

    if is_json:
        click.echo(json.dumps({
            "usecaseId": usecase_id,
            "templateId": template_id,
            "position": position,
            "stepsCreated": response.steps_created,
            "secretsSet": secrets_set,
            "missingSecrets": missing_secrets,
            **({"secretsFailed": secrets_failed} if secrets_failed else {}),
        }, indent=2))
    else:
        where = "end" if position is None else str(position)
        click.echo(f"✓ Inserted {response.steps_created} step(s) from template {template_id} at position {where}")
        if secrets_failed:
            click.echo(f"✗ Failed to set secrets: {', '.join(secrets_failed)}", err=True)
        if missing_secrets:
            click.echo(f"⚠ Missing secrets (set in UI or pass --secret): {', '.join(missing_secrets)}")

    raise SystemExit(1 if secrets_failed else 0)


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
