"""Click command group for team member management."""

import click

from qa_studio_cli.api.client import require_auth
from qa_studio_cli.models.errors import ApiError
from qa_studio_cli.models.permissions import Member


@click.group()
def members():
    """Manage team members."""
    pass


@members.command("add")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID")
@click.option("--email", required=True, help="User email to add")
@click.option(
    "--role",
    type=click.Choice(["Admin", "Editor", "Viewer"], case_sensitive=True),
    required=True,
    help="Role to assign",
)
@click.pass_context
def add_member(ctx, team_id, email, role):
    """Add a member to a team."""
    client = ctx.obj["client"]
    body = {"email": email, "role": role}

    try:
        data = client.post(f"/teams/{team_id}/members", json_body=body)
        member = Member.model_validate(data)
        click.echo(f"✓ Added {member.email} to team as {member.role}.")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


@members.command("remove")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID")
@click.option("--user", "user_id", required=True, help="User ID to remove")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def remove_member(ctx, team_id, user_id, yes):
    """Remove a member from a team."""
    client = ctx.obj["client"]

    if not yes:
        if not click.confirm(f"Remove user {user_id} from team {team_id}?"):
            click.echo("Aborted.")
            return

    try:
        client.delete(f"/teams/{team_id}/members/{user_id}")
        click.echo(f"✓ User {user_id} removed from team {team_id}.")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


@members.command("set-role")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID")
@click.option("--user", "user_id", required=True, help="User ID")
@click.option(
    "--role",
    type=click.Choice(["Admin", "Editor", "Viewer"], case_sensitive=True),
    required=True,
    help="New role to assign",
)
@click.pass_context
def set_role(ctx, team_id, user_id, role):
    """Update a member's role within a team."""
    client = ctx.obj["client"]
    body = {"role": role}

    try:
        data = client.patch(f"/teams/{team_id}/members/{user_id}", json_body=body)
        member = Member.model_validate(data)
        click.echo(f"✓ Updated {member.email} to {member.role} in team {team_id}.")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)


@members.command("list")
@require_auth
@click.option("--team", "team_id", required=True, help="Team ID")
@click.pass_context
def list_members(ctx, team_id):
    """List all members of a team."""
    client = ctx.obj["client"]

    try:
        data = client.get(f"/teams/{team_id}/members")
        items = data.get("members", data) if isinstance(data, dict) else data
        members_list = [Member.model_validate(item) for item in items]

        if not members_list:
            click.echo("No members found.")
            return

        # Header
        email_w = max(len(m.email) for m in members_list)
        uid_w = max(len(m.user_id) for m in members_list)
        email_w = max(email_w, 5)
        uid_w = max(uid_w, 7)

        header = f"{'User ID':<{uid_w}}  {'Email':<{email_w}}  {'Role':<7}"
        click.echo(header)
        click.echo("─" * len(header))

        for m in members_list:
            click.echo(f"{m.user_id:<{uid_w}}  {m.email:<{email_w}}  {m.role:<7}")
    except ApiError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        raise SystemExit(1)
