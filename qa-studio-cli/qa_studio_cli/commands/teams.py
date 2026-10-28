"""Click command group for team management."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.models.errors import ApiError
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

    try:
        data = client.post("/teams", json_body=body)
        team = Team.model_validate(data)
        click.echo(f"✓ Team created: {team.name} (ID: {team.id})")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


@teams.command("delete")
@require_auth
@click.option("--id", "team_id", required=True, help="Team ID to delete")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_team(ctx, team_id, yes):
    """Delete a team."""
    client = ctx.obj["client"]

    if not yes:
        if not click.confirm(f"Delete team {team_id}?"):
            click.echo("Aborted.")
            return

    try:
        client.delete(f"/teams/{team_id}")
        click.echo(f"✓ Team {team_id} deleted.")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


@teams.command("list")
@require_auth
@click.pass_context
def list_teams(ctx):
    """List all teams."""
    client = ctx.obj["client"]

    try:
        data = client.get("/teams")
        items = data.get("teams", data) if isinstance(data, dict) else data
        teams_list = [Team.model_validate(item) for item in items]

        if not teams_list:
            click.echo("No teams found.")
            return

        # Header
        id_w = max(len(t.id) for t in teams_list)
        name_w = max(len(t.name) for t in teams_list)
        id_w = max(id_w, 2)
        name_w = max(name_w, 4)

        header = f"{'ID':<{id_w}}  {'Name':<{name_w}}  {'Members':>7}  {'Apps':>4}"
        click.echo(header)
        click.echo("─" * len(header))

        for t in teams_list:
            click.echo(
                f"{t.id:<{id_w}}  {t.name:<{name_w}}  "
                f"{t.member_count:>7}  {t.application_count:>4}"
            )
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


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

    try:
        data = client.post(f"/teams/{team_id}/shared-access", json_body=body)
        grant = SharedAccessGrant.model_validate(data)
        click.echo(
            f"✓ Granted {grant.access_level} access to team "
            f"{grant.target_team_name} (grant: {grant.grant_id})"
        )
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


@teams.command("revoke-access")
@require_auth
@click.option("--team", "team_id", required=True, help="Source team ID (owner)")
@click.option("--target-team", required=True, help="Target team ID")
@click.option("--app", "app_id", required=True, help="Application ID")
@click.pass_context
def revoke_access(ctx, team_id, target_team, app_id):
    """Revoke shared access to an application from another team."""
    client = ctx.obj["client"]

    try:
        client.delete(
            f"/teams/{team_id}/shared-access/{target_team}/applications/{app_id}"
        )
        click.echo(f"✓ Access revoked for team {target_team} on application {app_id}.")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


@teams.command("list-access")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID to list shared access for")
@click.pass_context
def list_access(ctx, team_id):
    """List shared access grants for a team's applications."""
    client = ctx.obj["client"]

    try:
        data = client.get(f"/teams/{team_id}/shared-access")
        items = data.get("grants", data) if isinstance(data, dict) else data
        grants = [SharedAccessGrant.model_validate(item) for item in items]

        if not grants:
            click.echo("No shared access grants found.")
            return

        # Header
        gid_w = max(len(g.grant_id) for g in grants)
        team_w = max(len(g.target_team_name) for g in grants)
        gid_w = max(gid_w, 8)
        team_w = max(team_w, 11)

        header = f"{'Grant ID':<{gid_w}}  {'Target Team':<{team_w}}  {'Level':<7}"
        click.echo(header)
        click.echo("─" * len(header))

        for g in grants:
            click.echo(f"{g.grant_id:<{gid_w}}  {g.target_team_name:<{team_w}}  {g.access_level:<7}")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)
