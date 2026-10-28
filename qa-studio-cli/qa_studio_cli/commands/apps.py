"""Click command group for application management (admin operations)."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.models.errors import ApiError


@click.group()
def apps():
    """Manage applications (admin operations)."""
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
