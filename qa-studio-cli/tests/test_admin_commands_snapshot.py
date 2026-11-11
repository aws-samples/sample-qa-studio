"""Byte-exact output snapshots of the members / teams / users commands.

Written before the shared-helper refactor (codebase-health C4) so the
refactor provably keeps every table, message and exit code.  Click 8 mixes
stderr into ``result.output``.
"""
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.errors import ApiError


def run(client, args, input_text=None):
    with patch("qa_studio_cli.api.client.config_exists", return_value=True), \
         patch("qa_studio_cli.api.client.load_config") as cfg, \
         patch("qa_studio_cli.api.client.get_valid_token", return_value="t"), \
         patch("qa_studio_cli.api.client.ApiClient", return_value=client):
        cfg.return_value = MagicMock(api_url="https://api.example.com")
        return CliRunner().invoke(cli, args, input=input_text)


MEMBERS = {"members": [
    {"user_id": "u-1", "email": "alice@example.com", "role": "Editor"},
    {"user_id": "user-0002", "email": "bo@x.io", "role": "Viewer"},
]}
TEAMS = {"teams": [
    {"id": "t-1", "name": "Alpha", "member_count": 3, "application_count": 12},
    {"id": "team-0002", "name": "B", "member_count": 10, "application_count": 0},
]}
GRANTS = {"grants": [
    {"grant_id": "g-1", "target_team_id": "t-2", "target_team_name": "Beta team", "access_level": "view"},
]}
USERS = {"users": [
    {"user_id": "u-1", "email": "alice@example.com", "teams": [{"name": "Alpha", "role": "Editor"}]},
    {"user_id": "u-2", "email": "b@x.io", "teams": []},
]}


@pytest.mark.parametrize("args,response,expected", [
    (["members", "list", "--team", "t-1"], MEMBERS,
     "User ID    Email              Role   \n"
     "─────────────────────────────────────\n"
     "u-1        alice@example.com  Editor \n"
     "user-0002  bo@x.io            Viewer \n"),
    (["members", "list", "--team", "t-1"], {"members": []}, "No members found.\n"),
    (["teams", "list"], TEAMS,
     "ID         Name   Members  Apps\n"
     "───────────────────────────────\n"
     "t-1        Alpha        3    12\n"
     "team-0002  B           10     0\n"),
    (["teams", "list"], [], "No teams found.\n"),
    (["teams", "list-access", "--team", "t-1"], GRANTS,
     "Grant ID  Target Team  Level  \n"
     "──────────────────────────────\n"
     "g-1       Beta team    view   \n"),
    (["teams", "list-access", "--team", "t-1"], {"grants": []}, "No shared access grants found.\n"),
    (["users", "list"], USERS,
     "User ID  Email              Teams\n"
     "─────────────────────────────────\n"
     "u-1      alice@example.com  Alpha (Editor)\n"
     "u-2      b@x.io             —\n"),
    (["users", "list"], {"users": []}, "No users found.\n"),
])
def test_list_tables(args, response, expected):
    client = MagicMock()
    client.get.return_value = response
    result = run(client, args)
    assert result.exit_code == 0
    assert result.output == expected


@pytest.mark.parametrize("method,args,response,expected", [
    ("post", ["members", "add", "--team", "t-1", "--email", "a@x", "--role", "Editor"],
     {"user_id": "u", "email": "a@x", "role": "Editor"}, "✓ Added a@x to team as Editor.\n"),
    ("patch", ["members", "set-role", "--team", "t-1", "--user", "u", "--role", "Viewer"],
     {"user_id": "u", "email": "a@x", "role": "Viewer"}, "✓ Updated a@x to Viewer in team t-1.\n"),
    ("delete", ["members", "remove", "--team", "t-1", "--user", "u", "-y"], None, "✓ User u removed from team t-1.\n"),
    ("post", ["teams", "create", "--name", "Alpha"], {"id": "t-9", "name": "Alpha"}, "✓ Team created: Alpha (ID: t-9)\n"),
    ("delete", ["teams", "delete", "--id", "t-9", "-y"], None, "✓ Team t-9 deleted.\n"),
    ("post", ["teams", "grant-access", "--team", "t-1", "--target-team", "t-2", "--app", "a-1", "--level", "view"],
     {"grant_id": "g-1", "target_team_id": "t-2", "target_team_name": "Beta", "access_level": "view"},
     "✓ Granted view access to team Beta (grant: g-1)\n"),
    ("delete", ["teams", "revoke-access", "--team", "t-1", "--target-team", "t-2", "--app", "a-1"], None,
     "✓ Access revoked for team t-2 on application a-1.\n"),
    ("patch", ["users", "assign", "--user", "u", "--team", "t-1", "--role", "Admin"], None,
     "✓ User u assigned to team t-1 as Admin.\n"),
])
def test_write_messages(method, args, response, expected):
    client = MagicMock()
    getattr(client, method).return_value = response
    result = run(client, args)
    assert result.exit_code == 0
    assert result.output == expected


@pytest.mark.parametrize("method,args", [
    ("get", ["members", "list", "--team", "t-1"]),
    ("post", ["members", "add", "--team", "t-1", "--email", "a@x", "--role", "Editor"]),
    ("delete", ["members", "remove", "--team", "t-1", "--user", "u", "-y"]),
    ("patch", ["members", "set-role", "--team", "t-1", "--user", "u", "--role", "Viewer"]),
    ("get", ["teams", "list"]),
    ("post", ["teams", "create", "--name", "Alpha"]),
    ("delete", ["teams", "delete", "--id", "t-9", "-y"]),
    ("post", ["teams", "grant-access", "--team", "t-1", "--target-team", "t-2", "--app", "a", "--level", "full"]),
    ("delete", ["teams", "revoke-access", "--team", "t-1", "--target-team", "t-2", "--app", "a"]),
    ("get", ["teams", "list-access", "--team", "t-1"]),
    ("get", ["users", "list"]),
    ("patch", ["users", "assign", "--user", "u", "--team", "t", "--role", "Viewer"]),
])
def test_api_errors_exit_1_with_the_message(method, args):
    client = MagicMock()
    getattr(client, method).side_effect = ApiError(403, "Forbidden")
    result = run(client, args)
    assert result.exit_code == 1
    assert "Forbidden" in result.output


@pytest.mark.parametrize("args,prompt", [
    (["members", "remove", "--team", "t-1", "--user", "u"], "Remove user u from team t-1? [y/N]: n\nAborted.\n"),
    (["teams", "delete", "--id", "t-9"], "Delete team t-9? [y/N]: n\nAborted.\n"),
])
def test_declined_confirmation_aborts_without_calling_the_api(args, prompt):
    client = MagicMock()
    result = run(client, args, input_text="n\n")
    assert result.exit_code == 0
    assert result.output == prompt
    client.delete.assert_not_called()
