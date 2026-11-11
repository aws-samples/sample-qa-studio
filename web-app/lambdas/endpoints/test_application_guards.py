"""Guards on moving a use case and deleting an application (task 08).

- ``POST /applications/{id}/usecases`` returns ``409`` (and writes nothing) when a
  use case moved in from another application has steps referencing a dataset of
  its current application; same-application association is unaffected.
- ``DELETE /applications/{id}`` deletes the application's Secrets Manager secrets
  (listed by the ``application_id`` tag) before the partition sweep; a failing
  ``delete_secret`` is logged and the delete still returns ``204``; the existing
  ``revoke_access`` audit line gains ``details.secrets_deleted``.
"""
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

os.environ.setdefault("TABLE_NAME", "test-table")

from authz_test_support import APP_ID, TEAM_A, TEAM_B, make_event, owned_resources  # noqa: E402
from fake_table import FakeTable  # noqa: E402
from handlers import associate_usecases, delete_application  # noqa: E402

WRITE = "api/applications.write"
OTHER_APP = "app-other"
PREFIX = "p"
APP_PREFIX = f"{PREFIX}/application/{APP_ID}/"


def _body(response):
    return json.loads(response["body"])


def _client_error(code, operation):
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------


def _assoc(usecase_id, app_id):
    return {"pk": f"APPLICATION#{app_id}", "sk": f"USECASE#{usecase_id}", "associated_at": "t", "environment": ""}


def _usecase(usecase_id, name, app_id):
    return {"pk": "USECASES", "sk": f"USECASE#{usecase_id}", "id": usecase_id, "name": name,
            "application_id": app_id, "owner_team_id": TEAM_A}


def _step(usecase_id, step_id, sort, step_type="repeat", **extra):
    item = {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}", "id": step_id, "sort": sort,
            "step_type": step_type, "instruction": f"instruction {step_id}"}
    item.update(extra)
    return item


def _metadata(app_id, usecase_count=0):
    return {"pk": f"APPLICATION#{app_id}", "sk": "METADATA", "id": app_id, "name": app_id,
            "owner_team_id": TEAM_A, "usecase_count": usecase_count}


# ---------------------------------------------------------------------------
# POST /applications/{id}/usecases
# ---------------------------------------------------------------------------


# Use cases: uc-same already in APP_ID; uc-ref / uc-ref2 / uc-plain belong to OTHER_APP.
USECASE_OWNERS = {
    "uc-same": {"application_id": APP_ID, "owner_team_id": TEAM_A, "created_by": None},
    "uc-ref": {"application_id": OTHER_APP, "owner_team_id": TEAM_A, "created_by": None},
    "uc-ref2": {"application_id": OTHER_APP, "owner_team_id": TEAM_A, "created_by": None},
    "uc-plain": {"application_id": OTHER_APP, "owner_team_id": TEAM_A, "created_by": None},
    "uc-orphan": {"application_id": None, "owner_team_id": None, "created_by": None},
}


class _CountingTable(FakeTable):
    def __init__(self, items):
        super().__init__(items)
        self.queried_pks = []

    def query(self, KeyConditionExpression, **kw):  # noqa: N803
        self.queried_pks.append(KeyConditionExpression._values[0]._values[1]
                                if KeyConditionExpression.expression_operator == "AND"
                                else KeyConditionExpression._values[1])
        return super().query(KeyConditionExpression, **kw)


def _associate_table():
    return _CountingTable([
        _metadata(APP_ID, usecase_count=1), _metadata(OTHER_APP, usecase_count=3),
        _assoc("uc-same", APP_ID),
        _assoc("uc-ref", OTHER_APP), _assoc("uc-ref2", OTHER_APP), _assoc("uc-plain", OTHER_APP),
        _usecase("uc-same", "Same app", APP_ID),
        _usecase("uc-ref", "Zeta checkout", OTHER_APP),
        _usecase("uc-ref2", "Alpha login", OTHER_APP),
        _usecase("uc-plain", "Plain", OTHER_APP),
        {"pk": "USECASES", "sk": "USECASE#uc-orphan", "id": "uc-orphan", "name": "Orphan"},
        # uc-same references a dataset of APP_ID — allowed, it is not moving.
        _step("uc-same", "s0", 1, dataset_id="ds-home"),
        # uc-ref: two dataset refs (out of sort order) plus an inline repeat and a child.
        _step("uc-ref", "s2", 3, dataset_id="ds-b"),
        _step("uc-ref", "s1", 1, dataset_id="ds-a"),
        _step("uc-ref", "s3", 2, repeat_columns=["a"], repeat_rows=[["1"]]),
        _step("uc-ref", "s4", 4, step_type="navigation", parent_step_id="s3"),
        # uc-ref2: one ref; empty dataset_id does not count.
        _step("uc-ref2", "s5", 1, dataset_id="ds-c"),
        _step("uc-ref2", "s6", 2, dataset_id=""),
        # uc-plain: inline repeat only.
        _step("uc-plain", "s7", 1, repeat_columns=["a"], repeat_rows=[["1"]]),
        # uc-orphan: stale reference to a dataset of whatever app it used to be in.
        _step("uc-orphan", "s8", 1, dataset_id="ds-stale"),
    ])


def _associate(table, usecase_ids, caller="editor_a", action=None, app_id=APP_ID):
    body = {"usecase_ids": usecase_ids}
    if action:
        body["action"] = action
    event = make_event(caller=caller, path={"id": app_id}, body=body, scopes=WRITE)

    def app_owner(requested):
        return TEAM_A if requested in (APP_ID, OTHER_APP) else None

    with owned_resources(usecases=USECASE_OWNERS), \
            patch("permissions_repo.get_usecase_owner", side_effect=lambda u, include_creator=False: USECASE_OWNERS.get(u)), \
            patch("permissions_repo.get_app_owner", side_effect=app_owner), \
            patch("permissions_repo.list_shared_access", return_value=[]), \
            patch.object(associate_usecases, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return associate_usecases.handle(event)


class TestAssociateDatasetGuard:
    def test_move_with_dataset_references_returns_409_body(self):
        table = _associate_table()
        response = _associate(table, ["uc-plain", "uc-ref", "uc-ref2"])
        assert response["statusCode"] == 409, response["body"]
        assert _body(response) == {
            "error": "use case references application datasets",
            "usecases": [
                {"usecase_id": "uc-ref2", "name": "Alpha login",
                 "steps": [{"id": "s5", "instruction": "instruction s5"}]},
                {"usecase_id": "uc-ref", "name": "Zeta checkout",
                 "steps": [{"id": "s1", "instruction": "instruction s1"},
                           {"id": "s2", "instruction": "instruction s2"}]},
            ],
        }

    def test_409_writes_nothing(self):
        table = _associate_table()
        before = {k: dict(v) for k, v in table.items.items()}
        _associate(table, ["uc-plain", "uc-ref"])
        assert table.items == before
        assert table.put_calls == [] and table.update_calls == [] and table.delete_calls == []

    def test_orphan_with_stale_reference_is_blocked(self):
        response = _associate(_associate_table(), ["uc-orphan"], caller="admin")
        assert response["statusCode"] == 409
        assert [u["usecase_id"] for u in _body(response)["usecases"]] == ["uc-orphan"]

    def test_move_without_dataset_references_succeeds(self):
        table = _associate_table()
        response = _associate(table, ["uc-plain"])
        assert response["statusCode"] == 200, response["body"]
        assert _body(response) == {"status": "usecases associated", "count": 1}
        assert table.get(f"APPLICATION#{APP_ID}", "USECASE#uc-plain") is not None
        assert table.get("USECASES", "USECASE#uc-plain")["application_id"] == APP_ID
        assert table.get(f"APPLICATION#{APP_ID}", "METADATA")["usecase_count"] == 2

    def test_same_application_with_dataset_reference_is_unaffected(self):
        table = _associate_table()
        response = _associate(table, ["uc-same"])
        assert response["statusCode"] == 200, response["body"]
        # Not a move: the steps of uc-same are never queried.
        assert table.queried_pks == []
        assert table.get(f"APPLICATION#{APP_ID}", "USECASE#uc-same") is not None

    def test_only_moved_usecases_are_queried(self):
        table = _associate_table()
        _associate(table, ["uc-same", "uc-plain", "uc-ref"])
        assert sorted(table.queried_pks) == ["USECASE#uc-plain", "USECASE#uc-ref"]

    def test_remove_action_ignores_dataset_references(self):
        table = _associate_table()
        response = _associate(table, ["uc-same"], action="remove")
        assert response["statusCode"] == 200, response["body"]
        assert table.get(f"APPLICATION#{APP_ID}", "USECASE#uc-same") is None

    def test_other_team_editor_denied_before_any_read(self):
        table = FakeTable()
        response = _associate(table, ["uc-ref"], caller="editor_b")
        assert response["statusCode"] in (403, 404)


# ---------------------------------------------------------------------------
# DELETE /applications/{id}
# ---------------------------------------------------------------------------


def _delete_table():
    return FakeTable([
        _metadata(APP_ID, usecase_count=1),
        {"pk": "APPLICATIONS", "sk": f"APPLICATION#{APP_ID}", "id": APP_ID},
        _assoc("uc-same", APP_ID),
        _usecase("uc-same", "Same app", APP_ID),
        {"pk": f"APPLICATION#{APP_ID}", "sk": "DATASET#ds-1", "dataset_id": "ds-1"},
    ])


def _secret(name):
    return {"Name": name, "Description": "d"}


@pytest.fixture
def secrets_client(monkeypatch):
    monkeypatch.setenv("SECRET_PREFIX", PREFIX)
    client = MagicMock()
    client.list_secrets.return_value = {"SecretList": [
        _secret(f"{APP_PREFIX}admin_password"),
        _secret(f"{APP_PREFIX}api_key"),
        _secret(f"{PREFIX}/application/other-app/admin_password"),  # tag collision, other prefix
    ]}
    return client


def _delete(table, secrets_client, caller="lead_a", shares=None):
    event = make_event(caller=caller, path={"id": APP_ID}, scopes=WRITE)
    with owned_resources(shares=shares), \
            patch("permissions_repo.get_app_owner", return_value=TEAM_A), \
            patch("permissions_repo.list_shared_access", return_value=list(shares or [])), \
            patch("permissions_repo.revoke_shared_access") as revoke, \
            patch("handlers.delete_application.log_permission_change") as audit, \
            patch.object(delete_application, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        boto_mock.client.return_value = secrets_client
        response = delete_application.handle(event)
    return response, revoke, audit, boto_mock


class TestDeleteApplicationSecrets:
    def test_deletes_tagged_secrets_without_recovery(self, secrets_client):
        table = _delete_table()
        response, _, _, boto_mock = _delete(table, secrets_client)
        assert response["statusCode"] == 204
        assert response["body"] == ""
        boto_mock.client.assert_called_once_with("secretsmanager")
        secrets_client.list_secrets.assert_called_once_with(Filters=[
            {"Key": "tag-key", "Values": ["application_id"]},
            {"Key": "tag-value", "Values": [APP_ID]},
        ])
        deleted = [c.kwargs for c in secrets_client.delete_secret.call_args_list]
        assert deleted == [
            {"SecretId": f"{APP_PREFIX}admin_password", "ForceDeleteWithoutRecovery": True},
            {"SecretId": f"{APP_PREFIX}api_key", "ForceDeleteWithoutRecovery": True},
        ]
        # Partition sweep still happens.
        assert table.get(f"APPLICATION#{APP_ID}", "METADATA") is None
        assert table.get("APPLICATIONS", f"APPLICATION#{APP_ID}") is None
        assert table.get(f"APPLICATION#{APP_ID}", "USECASE#uc-same") is None
        assert "application_id" not in table.get("USECASES", "USECASE#uc-same")

    def test_secrets_deleted_before_partition_sweep(self, secrets_client):
        order = []
        table = _delete_table()
        original_delete = table.delete_item
        table.delete_item = lambda **kw: (order.append("table"), original_delete(**kw))[1]
        secrets_client.delete_secret.side_effect = lambda **kw: order.append("secret")
        _delete(table, secrets_client)
        assert order[:2] == ["secret", "secret"]
        assert "table" in order[2:]

    def test_partial_secrets_manager_failure_still_returns_204(self, secrets_client, caplog):
        secrets_client.delete_secret.side_effect = [
            _client_error("InternalServiceError", "DeleteSecret"), {}]
        table = _delete_table()
        with caplog.at_level("ERROR"):
            response, _, _, _ = _delete(table, secrets_client)
        assert response["statusCode"] == 204
        assert secrets_client.delete_secret.call_count == 2
        assert table.get(f"APPLICATION#{APP_ID}", "METADATA") is None
        assert any("InternalServiceError" in r.getMessage() for r in caplog.records)

    def test_list_failure_is_logged_and_delete_continues(self, secrets_client, caplog):
        secrets_client.list_secrets.side_effect = _client_error("AccessDeniedException", "ListSecrets")
        table = _delete_table()
        with caplog.at_level("ERROR"):
            response, _, _, _ = _delete(table, secrets_client)
        assert response["statusCode"] == 204
        secrets_client.delete_secret.assert_not_called()
        assert table.get(f"APPLICATION#{APP_ID}", "METADATA") is None
        assert any("AccessDeniedException" in r.getMessage() for r in caplog.records)

    def test_no_secrets(self, secrets_client):
        secrets_client.list_secrets.return_value = {"SecretList": []}
        response, _, _, _ = _delete(_delete_table(), secrets_client)
        assert response["statusCode"] == 204
        secrets_client.delete_secret.assert_not_called()

    def test_audit_line_carries_secrets_deleted_count(self, secrets_client):
        shares = [{"app_id": APP_ID, "target_team_id": TEAM_B, "level": "view", "grant_id": "g-1"},
                  {"app_id": "app-x", "target_team_id": TEAM_B, "level": "view", "grant_id": "g-2"}]
        response, revoke, audit, _ = _delete(_delete_table(), secrets_client, shares=shares)
        assert response["statusCode"] == 204
        revoke.assert_called_once_with(TEAM_A, TEAM_B, APP_ID)
        audit.assert_called_once()
        kwargs = audit.call_args.kwargs
        assert kwargs["action"] == "revoke_access"
        assert kwargs["target"] == {"owner_team_id": TEAM_A, "target_team_id": TEAM_B, "app_id": APP_ID}
        assert kwargs["details"] == {"grant_id": "g-1", "reason": "app_deleted", "secrets_deleted": 2}

    def test_audit_count_excludes_failed_deletes(self, secrets_client):
        secrets_client.delete_secret.side_effect = [
            _client_error("InternalServiceError", "DeleteSecret"), {}]
        shares = [{"app_id": APP_ID, "target_team_id": TEAM_B, "level": "view", "grant_id": "g-1"}]
        _, _, audit, _ = _delete(_delete_table(), secrets_client, shares=shares)
        assert audit.call_args.kwargs["details"]["secrets_deleted"] == 1

    def test_no_grants_emits_no_audit_line(self, secrets_client):
        _, revoke, audit, _ = _delete(_delete_table(), secrets_client)
        revoke.assert_not_called()
        audit.assert_not_called()

    def test_editor_cannot_delete_and_no_secret_is_touched(self, secrets_client):
        response, _, _, _ = _delete(_delete_table(), secrets_client, caller="editor_a")
        assert response["statusCode"] == 403
        secrets_client.list_secrets.assert_not_called()
        secrets_client.delete_secret.assert_not_called()
