"""Click command group for application management.

``apps reassign`` is the admin operation; the ``variables``, ``secrets`` and
``datasets`` sub-groups manage the application-level configuration every use
case of the application inherits (precedence: application < use case < CLI
run override; a repeat step references a dataset by ``dataset_id``).
Secret values are read from a hidden prompt or ``--value-file`` and are never
echoed or logged.
"""

import csv
import io
import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

import click

from qa_studio_cli.api.applications import READ_SCOPE, WRITE_SCOPE, ApplicationsAPI
from qa_studio_cli.api.client import require_auth
from qa_studio_cli.commands._admin_output import Column, confirmed, echo_table
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.runner.dataset_file import DatasetFileError, read_dataset_csv
from qa_studio_cli.validation import validate_repeat_dataset

#: Mirrors ``put_application_variables.VARIABLE_KEY_PATTERN`` on the server.
_VARIABLE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Mirrors ``secret_names.SECRET_KEY_PATTERN`` on the server.
_SECRET_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

OUTPUT_OPTION = click.option(
    "--output", "output_format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table", help="Output format (default: table)",
)


@contextmanager
def exit_on_app_api_error(scope: str) -> Iterator[None]:
    """``_admin_output.exit_on_api_error`` plus the scope the route needs on 403.

    Validation responses (``{error, errors: [...]}``) list every rule that
    failed; ``409`` dataset deletes list the referencing use cases.
    """
    try:
        yield
    except ApiError as e:
        click.echo(click.style(_format_api_error(e, scope), fg="red"), err=True)
        raise SystemExit(1)


def _format_api_error(e: ApiError, scope: str) -> str:
    data = e.response_data if isinstance(e.response_data, dict) else {}
    # 401/403/404 messages are written by ApiClient; other statuses carry the
    # server's ``error`` string, which the client does not pick up.
    if e.status_code not in (401, 403, 404) and data.get("error"):
        lines = [f"[{e.status_code}] {data['error']}"]
    else:
        lines = [str(e)]
    if e.status_code == 403:
        lines.append(f"This command needs the {scope} scope.")
    errors = data.get("errors")
    if isinstance(errors, list) and errors:
        lines.extend(f"  - {error}" for error in errors)
    usecases = data.get("usecases")
    if isinstance(usecases, list) and usecases:
        lines.append("Referenced by:")
        lines.extend(
            f"  - {usecase.get('name', '')} ({usecase.get('usecase_id', '')})" for usecase in usecases
        )
    return "\n".join(lines)


def _echo_json(payload: Any) -> None:
    click.echo(json.dumps(payload, indent=2))


@click.group()
def apps():
    """Manage applications and their shared configuration."""
    pass


@apps.command("reassign")
@require_auth
@click.option("--app", "app_id", required=True, help="Application ID to reassign")
@click.option("--to-team", "to_team_id", required=True, help="Target team ID")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reassign_app(ctx, app_id, to_team_id, yes):
    """Reassign an application to a different team (Admin-only)."""
    client = ctx.obj["client"]

    if not yes:
        if not click.confirm(
            f"Reassign application {app_id} to team {to_team_id}?"
        ):
            click.echo("Aborted.")
            return

    body = {"target_team_id": to_team_id}

    try:
        client.post(f"/applications/{app_id}/reassign", json_body=body)
        click.echo(f"✓ Application {app_id} reassigned to team {to_team_id}.")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# apps variables
# ---------------------------------------------------------------------------


@apps.group("variables")
def variables():
    """Application-level variables (inherited by its use cases)."""
    pass


def _parse_assignments(assignments: Sequence[str]) -> dict[str, str]:
    """``KEY=VALUE`` arguments → dict; the value may be empty or contain ``=``.

    Raises ``click.BadParameter`` (exit 2) for a missing ``=``, an empty or
    invalid key, or a key given twice.
    """
    result: dict[str, str] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise click.BadParameter(f"expected KEY=VALUE, got: {assignment!r}", param_hint="ASSIGNMENT")
        key, _, value = assignment.partition("=")
        if not key:
            raise click.BadParameter(f"empty key in {assignment!r}", param_hint="ASSIGNMENT")
        if not _VARIABLE_KEY_RE.match(key):
            raise click.BadParameter(
                f"{key!r} is not a valid variable key (letters, digits and underscores, "
                f"not starting with a digit)",
                param_hint="ASSIGNMENT",
            )
        if key in result:
            raise click.BadParameter(f"key {key!r} supplied more than once", param_hint="ASSIGNMENT")
        result[key] = value
    return result


@variables.command("list")
@require_auth
@click.argument("app_id")
@OUTPUT_OPTION
@click.pass_context
def list_variables(ctx, app_id, output_format):
    """List the application's variables."""
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(READ_SCOPE):
        rows = api.get_variables(app_id)
    if output_format == "json":
        _echo_json(rows)
        return
    if not rows:
        click.echo("No variables set on this application.")
        return
    echo_table(rows, [
        Column("Key", lambda v: v.get("key", "")),
        Column("Value", lambda v: v.get("value", ""), pad=False),
    ])


@variables.command("set")
@require_auth
@click.argument("app_id")
@click.argument("assignments", nargs=-1, required=True, metavar="KEY=VALUE...")
@click.pass_context
def set_variables(ctx, app_id, assignments):
    """Set one or more variables (KEY=VALUE), keeping the others.

    Reads the current list, merges the given keys and writes the whole list
    back; two concurrent writers lose each other's updates.
    """
    new_values = _parse_assignments(assignments)
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(WRITE_SCOPE):
        merged = _merge_variables(api.get_variables(app_id), new_values)
        api.put_variables(app_id, merged)
    click.echo(f"✓ Set {len(new_values)} variable(s) on application {app_id} ({len(merged)} total).")


def _merge_variables(current: List[dict], new_values: dict[str, str]) -> List[dict]:
    """Existing rows keep their position (value replaced); new keys are appended in argument order."""
    merged = [
        {"key": row.get("key", ""), "value": new_values.get(row.get("key", ""), row.get("value", ""))}
        for row in current
    ]
    existing = {row["key"] for row in merged}
    merged.extend({"key": key, "value": value} for key, value in new_values.items() if key not in existing)
    return merged


@variables.command("unset")
@require_auth
@click.argument("app_id")
@click.argument("keys", nargs=-1, required=True, metavar="KEY...")
@click.pass_context
def unset_variables(ctx, app_id, keys):
    """Remove one or more variables by key.

    Reads the current list, drops the given keys and writes the whole list
    back. Fails without writing when a key is not set.
    """
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(WRITE_SCOPE):
        current = api.get_variables(app_id)
        present = {row.get("key") for row in current}
        missing = [key for key in keys if key not in present]
        if missing:
            click.echo(
                click.style(f"Variable(s) not set on application {app_id}: {', '.join(missing)}", fg="red"),
                err=True,
            )
            raise SystemExit(1)
        remaining = [row for row in current if row.get("key") not in set(keys)]
        api.put_variables(app_id, remaining)
    click.echo(f"✓ Removed {len(set(keys))} variable(s) from application {app_id} ({len(remaining)} remaining).")


# ---------------------------------------------------------------------------
# apps secrets
# ---------------------------------------------------------------------------


@apps.group("secrets")
def secrets():
    """Application-level secrets (inherited by its use cases)."""
    pass


@secrets.command("list")
@require_auth
@click.argument("app_id")
@OUTPUT_OPTION
@click.pass_context
def list_secrets(ctx, app_id, output_format):
    """List the application's secret keys (values are never shown)."""
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(READ_SCOPE):
        rows = api.list_secrets(app_id)
    if output_format == "json":
        _echo_json(rows)
        return
    if not rows:
        click.echo("No secrets set on this application.")
        return
    echo_table(rows, [
        Column("Key", lambda s: s.get("key", "")),
        Column("Created At", lambda s: s.get("created_at", ""), pad=False),
    ])


def _read_secret_value(key: str, value_file: Optional[Path]) -> str:
    """The value from ``--value-file`` (one trailing newline removed) or a hidden prompt."""
    if value_file is not None:
        try:
            value = value_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise click.BadParameter(f"cannot read {value_file}: {exc}", param_hint="--value-file") from exc
        if value.endswith("\n"):
            value = value[:-1].removesuffix("\r")
        if not value:
            raise click.BadParameter("secret value must not be empty", param_hint="--value-file")
        return value
    value = click.prompt(f"Value for secret {key}", hide_input=True, default="", show_default=False)
    if not value:
        raise click.BadParameter("secret value must not be empty", param_hint="KEY")
    return value


@secrets.command("set")
@require_auth
@click.argument("app_id")
@click.argument("key")
@click.option(
    "--value-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
    help="Read the value from this file (one trailing newline is dropped) instead of prompting",
)
@click.pass_context
def set_secret(ctx, app_id, key, value_file):
    """Create or update one secret; the value is prompted (hidden) unless --value-file is given."""
    if not _SECRET_KEY_RE.match(key):
        raise click.BadParameter(
            f"{key!r} is not a valid secret key (letters, digits, '_', '.', '-'; at most 128 characters)",
            param_hint="KEY",
        )
    value = _read_secret_value(key, value_file)
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(WRITE_SCOPE):
        result = api.set_secrets(app_id, {key: value})
    outcome = "updated" if key in (result.get("updated") or []) else "created"
    click.echo(f"✓ Secret {key} {outcome} on application {app_id}.")


@secrets.command("delete")
@require_auth
@click.argument("app_id")
@click.argument("key")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_secret(ctx, app_id, key, yes):
    """Delete one secret (no recovery window)."""
    if not confirmed(f"Delete secret {key} from application {app_id}?", yes):
        return
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(WRITE_SCOPE):
        api.delete_secret(app_id, key)
    click.echo(f"✓ Secret {key} deleted from application {app_id}.")


# ---------------------------------------------------------------------------
# apps datasets
# ---------------------------------------------------------------------------


@apps.group("datasets")
def datasets():
    """Application datasets (tables repeat steps reference by dataset_id)."""
    pass


DATASET_OUTPUT_OPTION = click.option(
    "--output", "output_format",
    type=click.Choice(["table", "json", "csv"], case_sensitive=False),
    default="table", help="Output format (default: table; csv round-trips into --file)",
)
DATASET_FILE_OPTION = click.option(
    "--file", "dataset_file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Rows as .csv (header row names the columns) or .json ({\"columns\": [...], \"rows\": [[...]]})",
)


def load_dataset_file(path: Path) -> Dict[str, Any]:
    """``path`` (``.csv`` or ``.json``) → ``{"columns", "rows"}``, validated with the server's rules.

    CSV goes through ``runner.dataset_file.read_dataset_csv`` (the ``--dataset-file``
    parser); JSON must be an object with ``columns`` and ``rows``.  Raises
    ``DatasetFileError``.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_dataset_csv(str(path))
    if suffix != ".json":
        raise DatasetFileError(f"{path}: unsupported file type; use .csv or .json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetFileError(f"{path}: invalid JSON ({exc})") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise DatasetFileError(f"{path}: cannot read file ({exc})") from exc
    if not isinstance(data, dict) or "columns" not in data or "rows" not in data:
        raise DatasetFileError(f'{path}: JSON must be an object with "columns" and "rows"')
    errors = validate_repeat_dataset(data["columns"], data["rows"])
    if errors:
        raise DatasetFileError(f"{path}: " + "; ".join(errors))
    return {"columns": data["columns"], "rows": data["rows"]}


def _load_dataset_file_or_usage_error(path: Path) -> Dict[str, Any]:
    try:
        return load_dataset_file(path)
    except DatasetFileError as exc:
        raise click.UsageError(str(exc)) from exc


def _dataset_summary(dataset: Dict[str, Any]) -> str:
    columns = dataset.get("columns") or []
    rows = dataset.get("rows") or []
    return f"{dataset.get('name', '')} (ID: {dataset.get('dataset_id', '')}; {len(columns)} columns, {len(rows)} rows)"


@datasets.command("list")
@require_auth
@click.argument("app_id")
@OUTPUT_OPTION
@click.pass_context
def list_datasets(ctx, app_id, output_format):
    """List the application's datasets (counts only; use `get` for rows)."""
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(READ_SCOPE):
        rows = api.list_datasets(app_id)
    if output_format == "json":
        _echo_json(rows)
        return
    if not rows:
        click.echo("No datasets in this application.")
        return
    echo_table(rows, [
        Column("ID", lambda d: d.get("dataset_id", "")),
        Column("Name", lambda d: d.get("name", "")),
        Column("Columns", lambda d: d.get("column_count", 0), width=7, align=">"),
        Column("Rows", lambda d: d.get("row_count", 0), width=4, align=">"),
        Column("Updated At", lambda d: d.get("updated_at", ""), pad=False),
    ])


@datasets.command("get")
@require_auth
@click.argument("app_id")
@click.argument("dataset_id")
@DATASET_OUTPUT_OPTION
@click.pass_context
def get_dataset(ctx, app_id, dataset_id, output_format):
    """Show one dataset with its rows."""
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(READ_SCOPE):
        dataset = api.get_dataset(app_id, dataset_id)
    columns: List[str] = dataset.get("columns") or []
    rows: List[List[str]] = dataset.get("rows") or []
    if output_format == "json":
        _echo_json(dataset)
        return
    if output_format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
        click.echo(buffer.getvalue(), nl=False)
        return
    click.echo(f"ID:          {dataset.get('dataset_id', '')}")
    click.echo(f"Name:        {dataset.get('name', '')}")
    click.echo(f"Description: {dataset.get('description', '')}")
    click.echo(f"Updated At:  {dataset.get('updated_at', '')}")
    click.echo()
    if not columns:
        click.echo("(no columns)")
        return
    last = len(columns) - 1
    echo_table(rows, [
        Column(name, _cell(index), pad=index != last) for index, name in enumerate(columns)
    ])


def _cell(index: int):
    """Column accessor for ``echo_table`` over list rows (missing cells render empty)."""
    return lambda row: row[index] if index < len(row) else ""


@datasets.command("create")
@require_auth
@click.argument("app_id")
@click.argument("name")
@DATASET_FILE_OPTION
@click.option("--description", default="", help="Optional description")
@OUTPUT_OPTION
@click.pass_context
def create_dataset(ctx, app_id, name, dataset_file, description, output_format):
    """Create a dataset from a .csv or .json file."""
    if dataset_file is None:
        raise click.UsageError("Missing option '--file'.")
    table = _load_dataset_file_or_usage_error(dataset_file)
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(WRITE_SCOPE):
        dataset = api.create_dataset(app_id, {"name": name, "description": description, **table})
    if output_format == "json":
        _echo_json(dataset)
        return
    click.echo(f"✓ Dataset created: {_dataset_summary(dataset)}")


@datasets.command("update")
@require_auth
@click.argument("app_id")
@click.argument("dataset_id")
@click.option("--name", default=None, help="New name")
@click.option("--description", default=None, help="New description (pass '' to clear)")
@DATASET_FILE_OPTION
@OUTPUT_OPTION
@click.pass_context
def update_dataset(ctx, app_id, dataset_id, name, description, dataset_file, output_format):
    """Change a dataset's name, description and/or rows.

    The API replaces the whole dataset, so the current one is read first and
    only the given fields change.
    """
    if name is None and description is None and dataset_file is None:
        raise click.UsageError("Nothing to update: pass --name, --description and/or --file.")
    table = _load_dataset_file_or_usage_error(dataset_file) if dataset_file is not None else None
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(WRITE_SCOPE):
        current = api.get_dataset(app_id, dataset_id)
        payload = {
            "name": current.get("name", "") if name is None else name,
            "description": current.get("description", "") if description is None else description,
            "columns": current.get("columns") or [],
            "rows": current.get("rows") or [],
            **(table or {}),
        }
        dataset = api.update_dataset(app_id, dataset_id, payload)
    if output_format == "json":
        _echo_json(dataset)
        return
    click.echo(f"✓ Dataset updated: {_dataset_summary(dataset)}")


@datasets.command("delete")
@require_auth
@click.argument("app_id")
@click.argument("dataset_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_dataset(ctx, app_id, dataset_id, yes):
    """Delete a dataset; refused (409) while repeat steps reference it."""
    if not confirmed(f"Delete dataset {dataset_id} from application {app_id}?", yes):
        return
    api = ApplicationsAPI(ctx.obj["client"])
    with exit_on_app_api_error(WRITE_SCOPE):
        api.delete_dataset(app_id, dataset_id)
    click.echo(f"✓ Dataset {dataset_id} deleted from application {app_id}.")
