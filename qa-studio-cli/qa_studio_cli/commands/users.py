"""Click command group for user management (platform-level)."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.commands._admin_output import Column, echo_table, exit_on_api_error, list_items
from qa_studio_cli.models.permissions import UserWithTeams


@click.group()
def users():
    """Manage platform users."""
    pass


def _teams_cell(user: UserWithTeams) -> str:
    if not user.teams:
        return "—"
    return ", ".join(
        f"{t.get('name', t.get('team_id', '?'))} ({t.get('role', '?')})" for t in user.teams
    )


@users.command("list")
@require_auth
@click.pass_context
def list_users(ctx):
    """List all users with their team memberships."""
    client = ctx.obj["client"]
    with exit_on_api_error():
        data = client.get("/users")
        user_list = [UserWithTeams.model_validate(item) for item in list_items(data, "users")]
        if not user_list:
            click.echo("No users found.")
            return
        echo_table(user_list, [
            Column("User ID", lambda u: u.user_id),
            Column("Email", lambda u: u.email),
            Column("Teams", _teams_cell, pad=False),
        ])


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
    with exit_on_api_error():
        client.patch(f"/users/{user_id}", json_body={"team_id": team_id, "role": role})
        click.echo(f"✓ User {user_id} assigned to team {team_id} as {role}.")
