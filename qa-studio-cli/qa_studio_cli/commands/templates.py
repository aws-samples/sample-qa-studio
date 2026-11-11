"""Click command group for template management.

Templates are reusable step sequences (plus variables) such as "Login".
From the CLI you can list and inspect them, create one from a template
file, export one to a file, update one from an (edited) file, delete one,
and reference them by UUID in test JSON (``step_type: "template"``) or
insert them into an existing test (``qa-studio tests insert-template``).

Commands: ``list``, ``get``, ``create``, ``export``, ``update``, ``delete``.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.api.templates import TemplateAPI
from qa_studio_cli.importers.scanner import format_validation_errors
from qa_studio_cli.models.api import (
    ImportTemplateResponse,
    ReplaceTemplateResponse,
    TemplateModel,
    TemplateStepModel,
    TemplateUsageModel,
)
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.models.import_schema import ExportStep, TemplateFilePayload

FORMAT_OPTION = click.option(
    "--format", "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human", help="Output format (default: human)",
)


def secret_keys_of_steps(steps: list[TemplateStepModel]) -> list[str]:
    """Distinct ``secret_key`` values of ``secret`` steps, in step order."""
    keys: list[str] = []
    for step in steps:
        if step.step_type == "secret" and step.secret_key and step.secret_key not in keys:
            keys.append(step.secret_key)
    return keys


@dataclass
class TemplateBundle:
    """Metadata, raw steps (sorted by ``sort``) and variables of one template."""

    template: TemplateModel
    steps: list[dict[str, Any]]
    variables: list[dict[str, Any]]


def _load_template_bundle(api: TemplateAPI, template_id: str) -> TemplateBundle:
    """The three reads ``get``, ``export`` and ``update`` share (404 → ``ApiError``)."""
    return TemplateBundle(
        template=TemplateModel.model_validate(api.get_template(template_id)),
        steps=api.list_steps(template_id),
        variables=api.get_variables(template_id),
    )


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


@click.group()
def templates():
    """Manage templates (reusable step sequences)."""
    pass


@templates.command("list")
@require_auth
@FORMAT_OPTION
@click.pass_context
def list_templates(ctx, output_format):
    """List all templates with their step counts."""
    client = ctx.obj["client"]
    api = TemplateAPI(client)
    is_json = output_format == "json"
    try:
        items = [TemplateModel.model_validate(t) for t in api.list_templates()]
        if not items:
            click.echo(json.dumps([]) if is_json else "No templates found.")
            return

        step_counts = {item.id: len(api.list_steps(item.id)) for item in items}

        if is_json:
            click.echo(json.dumps(
                [{**item.model_dump(), "stepCount": step_counts[item.id]} for item in items], indent=2,
            ))
            return

        click.echo(f"{'ID':<40} {'Steps':>5}  {'Name':<30}  Category")
        click.echo(f"{'─' * 40} {'─' * 5}  {'─' * 30}  {'─' * 12}")
        for item in items:
            click.echo(f"{item.id:<40} {step_counts[item.id]:>5}  {item.name:<30}  {item.category}")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@templates.command("get")
@require_auth
@click.argument("id")
@FORMAT_OPTION
@click.pass_context
def get_template(ctx, id, output_format):
    """Show a template: metadata, ordered steps, variables, required secrets and the tests using it."""
    client = ctx.obj["client"]
    api = TemplateAPI(client)
    try:
        bundle = _load_template_bundle(api, id)
        item = bundle.template
        steps = [TemplateStepModel.model_validate(s) for s in bundle.steps]
        variables = bundle.variables
        secret_keys = secret_keys_of_steps(steps)
        usages = [TemplateUsageModel.model_validate(u) for u in api.get_usages(id)]

        if output_format == "json":
            click.echo(json.dumps({
                "template": item.model_dump(),
                "steps": [s.model_dump() for s in steps],
                "variables": variables,
                "secretKeys": secret_keys,
                "usages": [u.model_dump() for u in usages],
            }, indent=2))
            return

        click.echo(f"ID:          {item.id}")
        click.echo(f"Name:        {item.name}")
        click.echo(f"Description: {item.description}")
        click.echo(f"Category:    {item.category or '—'}")
        click.echo(f"Tags:        {', '.join(item.tags) if item.tags else '—'}")
        click.echo(f"Version:     {item.version}")
        click.echo(f"Created By:  {item.created_by}")
        click.echo(f"Created At:  {item.created_at}")

        click.echo(f"\nSteps ({len(steps)}):")
        if not steps:
            click.echo("  No steps defined.")
        for step in steps:
            click.echo(f"  {step.sort:>3}. [{step.step_type}] {step.instruction}")

        click.echo(f"\nVariables ({len(variables)}):")
        for variable in variables:
            click.echo(f"  {variable.get('key', '')} = {variable.get('value', '')}")

        click.echo(f"\nRequired secrets: {', '.join(secret_keys) if secret_keys else '—'}")

        click.echo(f"\nUsed by ({len(usages)}):")
        if not usages:
            click.echo("  —")
        for usage in usages:
            click.echo(f"  {usage.name} ({usage.usecase_id})")

    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


@templates.command("delete")
@require_auth
@click.argument("id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_template(ctx, id, yes):
    """Delete a template. Tests that use it keep their steps; only the template link is removed."""
    client = ctx.obj["client"]
    api = TemplateAPI(client)

    try:
        item = TemplateModel.model_validate(api.get_template(id))
        usages = api.get_usages(id)
    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if not yes:
        if usages:
            question = (f'Template "{item.name}" is used by {_plural(len(usages), "test")} '
                        f'(steps are kept, template link removed). Delete?')
        else:
            question = f'Template "{item.name}" is not used by any test. Delete?'
        if not click.confirm(question):
            click.echo("Aborted.")
            return

    try:
        api.delete_template(id)
        click.echo(f"✓ Template {id} deleted.")
    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)


def load_template_file(path: Path) -> tuple[TemplateFilePayload | None, list[str]]:
    """Read + validate a template file; ``(payload, [])`` or ``(None, errors)``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, [f"{path.name}: invalid JSON: {e}"]
    except OSError as e:
        return None, [f"{path.name}: cannot read file: {e}"]
    try:
        return TemplateFilePayload.model_validate(data), []
    except ValidationError as e:
        return None, format_validation_errors(e)


def _report_invalid_file(path: Path, errors: list[str], is_json: bool) -> None:
    """Shared by ``create`` and ``update``; exits 1."""
    if is_json:
        click.echo(json.dumps({"valid": False, "file": path.name, "errors": errors}, indent=2))
    else:
        click.echo(f"✗ {path.name} is not a valid template file:", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)
    raise SystemExit(1)


@templates.command("create")
@require_auth
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Validate the template file only, do not create")
@FORMAT_OPTION
@click.pass_context
def create_template(ctx, path, dry_run, output_format):
    """Create a template from a template JSON file (templateVersion 1.0)."""
    client = ctx.obj["client"]
    is_json = output_format == "json"

    payload, errors = load_template_file(path)
    if payload is None:
        _report_invalid_file(path, errors, is_json)

    secret_keys = payload.secret_keys()
    if dry_run:
        if is_json:
            click.echo(json.dumps({
                "valid": True, "file": path.name, "name": payload.template.name,
                "stepCount": len(payload.steps), "secretKeys": secret_keys,
            }, indent=2))
        else:
            click.echo(f"✓ {path.name} is valid: {payload.template.name} ({len(payload.steps)} step(s))")
            click.echo(f"  Required secrets: {', '.join(secret_keys) if secret_keys else '—'}")
        return

    try:
        data = TemplateAPI(client).import_template(payload.model_dump(by_alias=False))
        response = ImportTemplateResponse.model_validate(data)
    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if is_json:
        click.echo(json.dumps({"id": response.id, "name": response.name, "stepsCreated": response.steps_created}))
    else:
        click.echo(f"✓ Template created: {response.name} (ID: {response.id})")
        if secret_keys:
            click.echo(f"  Tests using this template need secrets: {', '.join(secret_keys)}")


#: Always first in an exported step, in this order; the rest follows alphabetically.
_EXPORT_LEADING_KEYS = ("id", "sort", "step_type", "instruction")

#: Authored per-step fields = the optional fields of ``ExportStep`` (the
#: server pins that list to ``COPYABLE_STEP_FIELDS``), minus the nesting
#: fields templates cannot have.
_EXPORT_STEP_FIELDS = tuple(
    name for name in ExportStep.model_fields
    if name not in _EXPORT_LEADING_KEYS and name not in ("steps", "parent_step_id")
)


def _export_step(raw: dict[str, Any], position: int) -> dict[str, Any]:
    """One template step as it appears in a template file (``id`` kept, ``sort`` renumbered)."""
    step: dict[str, Any] = {
        "id": raw.get("id", ""),
        "sort": position,
        "step_type": raw.get("step_type", ""),
        "instruction": raw.get("instruction", ""),
    }
    for field in sorted(_EXPORT_STEP_FIELDS):
        value = raw.get(field)
        if value is None or value == "":
            continue
        step[field] = value
    return step


def _export_payload(bundle: TemplateBundle) -> dict[str, Any]:
    """The template file (``templateVersion: "1.0"``) for ``bundle``."""
    template = bundle.template
    return {
        "templateVersion": "1.0",
        "template": {
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "tags": list(template.tags),
        },
        "steps": [_export_step(raw, position) for position, raw in enumerate(bundle.steps, start=1)],
        "variables": [{"key": v.get("key", ""), "value": v.get("value", "")} for v in bundle.variables],
    }


@templates.command("export")
@require_auth
@click.argument("id")
@click.option("--output", "output", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Write the template file here instead of stdout")
@click.pass_context
def export_template(ctx, id, output):
    """Export a template as a template file (steps carry their id for `templates update`)."""
    client = ctx.obj["client"]
    try:
        bundle = _load_template_bundle(TemplateAPI(client), id)
    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    payload = _export_payload(bundle)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if output is None:
        click.echo(text)
        return

    try:
        output.write_text(text + "\n", encoding="utf-8")
    except OSError as e:
        click.echo(f"✗ Cannot write {output}: {e}", err=True)
        raise SystemExit(1)
    click.echo(f"✓ Exported {bundle.template.name} ({_plural(len(payload['steps']), 'step')}) to {output}")


#: Metadata fields ``templates update`` compares (and ``PUT /templates/{id}`` sets).
_METADATA_FIELDS = ("name", "description", "category", "tags")


@dataclass
class UpdatePlan:
    """Client-side preview of what ``PUT /templates/{id}`` will do with a file."""

    created: int
    updated: int
    deleted: int
    metadata_changed: list[str]
    unknown_ids: list[str]  # ``steps[i]: id … does not belong …`` messages

    def as_json(self) -> dict[str, Any]:
        return {"created": self.created, "updated": self.updated, "deleted": self.deleted,
                "metadataChanged": self.metadata_changed}


def plan_update(payload: TemplateFilePayload, bundle: TemplateBundle, template_id: str) -> UpdatePlan:
    """Diff a template file against the current template — mirrors the server's matching by ``id``."""
    current_ids = {str(step.get("id")) for step in bundle.steps if step.get("id")}
    file_ids = {step.id for step in payload.steps if step.id is not None}
    unknown = [
        f"steps[{position}]: id {step.id} does not belong to template {template_id}"
        for position, step in enumerate(payload.steps)
        if step.id is not None and step.id not in current_ids
    ]
    current = bundle.template.model_dump()
    wanted = payload.template.model_dump()
    return UpdatePlan(
        created=sum(1 for step in payload.steps if step.id is None),
        updated=sum(1 for step in payload.steps if step.id is not None and step.id in current_ids),
        deleted=len(current_ids - file_ids),
        metadata_changed=[field for field in _METADATA_FIELDS if current.get(field) != wanted.get(field)],
        unknown_ids=unknown,
    )


@templates.command("update")
@require_auth
@click.argument("id")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Show the plan (updated / created / deleted steps) without writing")
@FORMAT_OPTION
@click.pass_context
def update_template(ctx, id, path, dry_run, output_format):
    """Update a template from a template file; steps are matched by their id (see `templates export`)."""
    client = ctx.obj["client"]
    is_json = output_format == "json"

    payload, errors = load_template_file(path)
    if payload is None:
        _report_invalid_file(path, errors, is_json)

    api = TemplateAPI(client)
    try:
        bundle = _load_template_bundle(api, id)
    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    plan = plan_update(payload, bundle, id)
    if plan.unknown_ids:
        if is_json:
            click.echo(json.dumps({"valid": False, "file": path.name, "errors": plan.unknown_ids}, indent=2))
        else:
            click.echo(f"✗ {path.name} does not match template {id}:", err=True)
            for error in plan.unknown_ids:
                click.echo(f"  - {error}", err=True)
        raise SystemExit(1)

    if dry_run:
        if is_json:
            click.echo(json.dumps({"valid": True, "plan": plan.as_json()}, indent=2))
        else:
            changed = ", ".join(plan.metadata_changed) if plan.metadata_changed else "—"
            click.echo(
                f'Plan for "{bundle.template.name}": {_plural(plan.updated, "step")} updated, '
                f"{plan.created} created, {plan.deleted} deleted; metadata changed: {changed}"
            )
        return

    try:
        data = api.replace_template(id, payload.model_dump(by_alias=False, exclude_none=True))
        response = ReplaceTemplateResponse.model_validate(data)
    except ApiError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if is_json:
        click.echo(json.dumps(response.model_dump(), indent=2))
    else:
        click.echo(
            f"✓ Template updated: {response.name} (version {response.version}; "
            f"{response.steps_updated} updated, {response.steps_created} created, {response.steps_deleted} deleted)"
        )
