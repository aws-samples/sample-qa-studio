"""Click command group for team member management."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.commands._admin_output import Column, confirmed, echo_table, exit_on_api_error, list_items
from qa_studio_cli.models.permissions import Member

ROLE_CHOICE = click.Choice(["Admin", "Editor", "Viewer"], case_sensitive=True)


@click.group()
def members():
    """Manage team members."""
    pass


@members.command("add")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID")
@click.option("--email", required=True, help="User email to add")
@click.option("--role", type=ROLE_CHOICE, required=True, help="Role to assign")
@click.pass_context
def add_member(ctx, team_id, email, role):
    """Add a member to a team."""
    client = ctx.obj["client"]
    with exit_on_api_error():
        data = client.post(f"/teams/{team_id}/members", json_body={"email": email, "role": role})
        member = Member.model_validate(data)
        click.echo(f"✓ Added {member.email} to team as {member.role}.")


@members.command("remove")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID")
@click.option("--user", "user_id", required=True, help="User ID to remove")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def remove_member(ctx, team_id, user_id, yes):
    """Remove a member from a team."""
    client = ctx.obj["client"]
    if not confirmed(f"Remove user {user_id} from team {team_id}?", yes):
        return
    with exit_on_api_error():
        client.delete(f"/teams/{team_id}/members/{user_id}")
        click.echo(f"✓ User {user_id} removed from team {team_id}.")


@members.command("set-role")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID")
@click.option("--user", "user_id", required=True, help="User ID")
@click.option("--role", type=ROLE_CHOICE, required=True, help="New role to assign")
@click.pass_context
def set_role(ctx, team_id, user_id, role):
    """Update a member's role within a team."""
    client = ctx.obj["client"]
    with exit_on_api_error():
        data = client.patch(f"/teams/{team_id}/members/{user_id}", json_body={"role": role})
        member = Member.model_validate(data)
        click.echo(f"✓ Updated {member.email} to {member.role} in team {team_id}.")


@members.command("list")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID")
@click.pass_context
def list_members(ctx, team_id):
    """List all members of a team."""
    client = ctx.obj["client"]
    with exit_on_api_error():
        data = client.get(f"/teams/{team_id}/members")
        members_list = [Member.model_validate(item) for item in list_items(data, "members")]
        if not members_list:
            click.echo("No members found.")
            return
        echo_table(members_list, [
            Column("User ID", lambda m: m.user_id),
            Column("Email", lambda m: m.email),
            Column("Role", lambda m: m.role, width=7),
        ])
