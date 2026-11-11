"""Click command group for team management."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.commands._admin_output import Column, confirmed, echo_table, exit_on_api_error, list_items
from qa_studio_cli.models.permissions import SharedAccessGrant, Team


@click.group()
def teams():
    """Manage teams."""
    pass


@teams.command("create")
@require_auth
@click.option("--name", required=True, help="Team name")
@click.option("--description", default=None, help="Optional team description")
@click.pass_context
def create_team(ctx, name, description):
    """Create a new team."""
    client = ctx.obj["client"]
    body = {"name": name}
    if description:
        body["description"] = description

    with exit_on_api_error():
        data = client.post("/teams", json_body=body)
        team = Team.model_validate(data)
        click.echo(f"✓ Team created: {team.name} (ID: {team.id})")


@teams.command("delete")
@require_auth
@click.option("--id", "team_id", required=True, help="Team ID to delete")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_team(ctx, team_id, yes):
    """Delete a team."""
    client = ctx.obj["client"]

    if not confirmed(f"Delete team {team_id}?", yes):
        return

    with exit_on_api_error():
        client.delete(f"/teams/{team_id}")
        click.echo(f"✓ Team {team_id} deleted.")


@teams.command("list")
@require_auth
@click.pass_context
def list_teams(ctx):
    """List all teams."""
    client = ctx.obj["client"]

    with exit_on_api_error():
        data = client.get("/teams")
        teams_list = [Team.model_validate(item) for item in list_items(data, "teams")]
        if not teams_list:
            click.echo("No teams found.")
            return
        echo_table(teams_list, [
            Column("ID", lambda t: t.id),
            Column("Name", lambda t: t.name),
            Column("Members", lambda t: t.member_count, width=7, align=">"),
            Column("Apps", lambda t: t.application_count, width=4, align=">"),
        ])


@teams.command("grant-access")
@require_auth
@click.option("--team", "team_id", required=True, help="Source team ID (owner)")
@click.option("--target-team", required=True, help="Target team ID (recipient)")
@click.option("--app", "app_id", required=True, help="Application ID to share")
@click.option(
    "--level",
    type=click.Choice(["view", "execute", "full"], case_sensitive=False),
    required=True,
    help="Access level to grant",
)
@click.pass_context
def grant_access(ctx, team_id, target_team, app_id, level):
    """Grant shared access to an application for another team."""
    client = ctx.obj["client"]
    body = {
        "target_team_id": target_team,
        "application_id": app_id,
        "access_level": level,
    }

    with exit_on_api_error():
        data = client.post(f"/teams/{team_id}/shared-access", json_body=body)
        grant = SharedAccessGrant.model_validate(data)
        click.echo(
            f"✓ Granted {grant.access_level} access to team "
            f"{grant.target_team_name} (grant: {grant.grant_id})"
        )


@teams.command("revoke-access")
@require_auth
@click.option("--team", "team_id", required=True, help="Source team ID (owner)")
@click.option("--target-team", required=True, help="Target team ID")
@click.option("--app", "app_id", required=True, help="Application ID")
@click.pass_context
def revoke_access(ctx, team_id, target_team, app_id):
    """Revoke shared access to an application from another team."""
    client = ctx.obj["client"]

    with exit_on_api_error():
        client.delete(
            f"/teams/{team_id}/shared-access/{target_team}/applications/{app_id}"
        )
        click.echo(f"✓ Access revoked for team {target_team} on application {app_id}.")


@teams.command("list-access")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID to list shared access for")
@click.pass_context
def list_access(ctx, team_id):
    """List shared access grants for a team's applications."""
    client = ctx.obj["client"]

    with exit_on_api_error():
        data = client.get(f"/teams/{team_id}/shared-access")
        grants = [SharedAccessGrant.model_validate(item) for item in list_items(data, "grants")]
        if not grants:
            click.echo("No shared access grants found.")
            return
        echo_table(grants, [
            Column("Grant ID", lambda g: g.grant_id),
            Column("Target Team", lambda g: g.target_team_name),
            Column("Level", lambda g: g.access_level, width=7),
        ])
