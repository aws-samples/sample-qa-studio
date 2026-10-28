"""Click command group for user management (platform-level)."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.models.permissions import UserWithTeams


@click.group()
def users():
    """Manage platform users."""
    pass


@users.command("list")
@require_auth
@click.pass_context
def list_users(ctx):
    """List all users with their team memberships."""
    client = ctx.obj["client"]

    try:
        data = client.get("/users")
        items = data.get("users", data) if isinstance(data, dict) else data
        user_list = [UserWithTeams.model_validate(item) for item in items]

        if not user_list:
            click.echo("No users found.")
            return

        # Header
        uid_w = max(len(u.user_id) for u in user_list)
        email_w = max(len(u.email) for u in user_list)
        uid_w = max(uid_w, 7)
        email_w = max(email_w, 5)

        header = f"{'User ID':<{uid_w}}  {'Email':<{email_w}}  {'Teams'}"
        click.echo(header)
        click.echo("─" * len(header))

        for u in user_list:
            if u.teams:
                teams_str = ", ".join(
                    f"{t.get('name', t.get('team_id', '?'))} ({t.get('role', '?')})"
                    for t in u.teams
                )
            else:
                teams_str = "—"
            click.echo(f"{u.user_id:<{uid_w}}  {u.email:<{email_w}}  {teams_str}")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


@users.command("assign")
@require_auth
@click.option("--user", "user_id", required=True, help="User ID")
@click.option("--team", "team_id", required=True, help="Team ID to assign user to")
@click.option(
    "--role",
    type=click.Choice(["Admin", "Editor", "Viewer"], case_sensitive=True),
    required=True,
    help="Role within the team",
)
@click.pass_context
def assign_user(ctx, user_id, team_id, role):
    """Assign a user to a team with a role."""
    client = ctx.obj["client"]
    body = {"team_id": team_id, "role": role}

    try:
        client.patch(f"/users/{user_id}", json_body=body)
        click.echo(f"✓ User {user_id} assigned to team {team_id} as {role}.")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)
