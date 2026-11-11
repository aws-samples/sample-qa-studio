"""Tests for ``test_platform = "electron"`` across the usecase lambdas.

Electron usecases are a new value on an existing attribute: create /
update / import must accept it (with no mobile fields), and the two
execute lambdas must refuse every trigger except ``ci_runner`` *before*
writing any record — the cloud worker has no display and cannot launch
a desktop app.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")
os.environ.setdefault("DEFAULT_REGION", "eu-central-1")

import platforms  # noqa: E402
from authz_test_support import make_event, resource_access_granted  # noqa: E402
from platforms import ELECTRON_CI_RUNNER_ONLY_ERROR, VALID_TEST_PLATFORMS, validate_test_platform  # noqa: E402


@pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership rules are covered by the *_access tests."""
    with resource_access_granted():
        yield


# ---------------------------------------------------------------------------
# Shared validator
# ---------------------------------------------------------------------------


class TestValidateTestPlatform:
    def test_known_values_pass(self):
        for value in ("web", "mobile", "electron"):
            assert validate_test_platform(value) is None

    def test_empty_means_web_and_passes(self):
        assert validate_test_platform("") is None
        assert validate_test_platform(None) is None

    def test_unknown_value_is_400(self):
        resp = validate_test_platform("tauri")
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"] == "test_platform must be one of: web, mobile, electron"

    def test_enum_is_the_single_source(self):
        assert VALID_TEST_PLATFORMS == ("web", "mobile", "electron")


# ---------------------------------------------------------------------------
# create_usecase
# ---------------------------------------------------------------------------


def _authz_event(body, scope="api/usecases.write", path=None):
    return make_event("editor_a", path=path, body=body, scopes=scope)


@pytest.fixture
def ddb_table():
    """Patch the high-level Table (update/import) and the low-level client
    (create_usecase writes through ``transact_write_items``)."""
    table = MagicMock()
    table.get_item.return_value = {"Item": {"owner_team_id": "team-1"}}
    client = MagicMock()
    with patch("boto3.resource") as res, patch("boto3.client", return_value=client):
        res.return_value.Table.return_value = table
        table.client = client
        yield table


class TestCreateUsecaseElectron:
    def test_accepts_electron_without_mobile_fields(self, ddb_table):
        from create_usecase import handler

        resp = handler(_authz_event({
            "name": "Harness smoke", "application_id": "app-1", "test_platform": "electron",
        }), None)
        assert resp["statusCode"] == 201, resp["body"]
        transact = ddb_table.client.transact_write_items.call_args[1]["TransactItems"]
        item = transact[0]["Put"]["Item"]
        assert item["test_platform"] == {"S": "electron"}
        assert item["starting_url"] == {"S": ""}
        assert "platform" not in item

    def test_rejects_unknown_platform(self, ddb_table):
        from create_usecase import handler

        resp = handler(_authz_event({
            "name": "x", "application_id": "app-1", "test_platform": "tauri",
        }), None)
        assert resp["statusCode"] == 400
        assert "test_platform must be one of" in json.loads(resp["body"])["error"]
        ddb_table.client.transact_write_items.assert_not_called()


class TestUpdateUsecaseElectron:
    def test_accepts_electron(self, ddb_table):
        from update_usecase import handler

        ddb_table.get_item.return_value = {
            "Item": {"application_id": "app-1", "owner_team_id": "team-1", "name": "x"},
        }
        ddb_table.update_item.return_value = {"Attributes": {"id": "u-1", "test_platform": "electron"}}
        resp = handler(_authz_event(
            {"name": "x", "description": "", "starting_url": "", "active": True,
             "test_platform": "electron"},
            path={"id": "u-1"},
        ), None)
        assert resp["statusCode"] == 200, resp["body"]
        values = ddb_table.update_item.call_args[1]["ExpressionAttributeValues"]
        assert values[":test_platform"] == "electron"

    def test_rejects_unknown_platform(self, ddb_table):
        from update_usecase import handler

        ddb_table.get_item.return_value = {
            "Item": {"application_id": "app-1", "owner_team_id": "team-1"},
        }
        resp = handler(_authz_event(
            {"name": "x", "test_platform": "tauri"}, path={"id": "u-1"},
        ), None)
        assert resp["statusCode"] == 400
        ddb_table.update_item.assert_not_called()


class TestImportUsecaseElectron:
    def _body(self, platform):
        return {
            "exportVersion": "1.0",
            "application_id": "app-1",
            "usecase": {"name": "Harness", "test_platform": platform, "application_id": "app-1"},
            "steps": [], "variables": [], "secrets": [],
        }

    def test_accepts_electron(self, ddb_table):
        from import_usecase import handler

        resp = handler(_authz_event(self._body("electron")), None)
        assert resp["statusCode"] in (200, 201), resp["body"]
        item = ddb_table.put_item.call_args_list[0][1]["Item"]
        assert item["test_platform"] == "electron"

    def test_rejects_unknown_platform(self, ddb_table):
        from import_usecase import handler

        resp = handler(_authz_event(self._body("tauri")), None)
        assert resp["statusCode"] == 400
        ddb_table.put_item.assert_not_called()


# ---------------------------------------------------------------------------
# execute_usecase
# ---------------------------------------------------------------------------


def _exec_event(trigger):
    return make_event("client_a", path={"id": "u-1"}, query={"trigger-type": trigger},
                      scopes="api/usecases.execute")


ELECTRON_ITEM = {
    "Item": {
        "starting_url": {"S": ""},
        "executing_region": {"S": "eu-central-1"},
        "model_id": {"S": "nova-act-v1.0"},
        "test_platform": {"S": "electron"},
        "bundle_id": {"S": "com.productharness.desktop"},
    }
}


class TestExecuteUsecaseElectron:
    @pytest.mark.parametrize("trigger", ["OnDemandHeadless", "Scheduled"])
    def test_cloud_triggers_rejected_before_any_write(self, trigger):
        from execute_usecase import handler

        with patch("execute_usecase.dynamodb") as ddb, patch("execute_usecase.eventbridge"), \
                patch("microvm_launch.get_microvm_client") as get_client:
            ddb.get_item.return_value = ELECTRON_ITEM
            resp = handler(_exec_event(trigger), None)
        assert resp["statusCode"] == 400
        assert json.loads(resp["body"])["error"] == ELECTRON_CI_RUNNER_ONLY_ERROR
        ddb.put_item.assert_not_called()
        get_client.assert_not_called()

    def test_ci_runner_creates_record_with_platform(self):
        from execute_usecase import handler

        with patch("execute_usecase.dynamodb") as ddb, patch("execute_usecase.eventbridge"):
            ddb.get_item.return_value = ELECTRON_ITEM
            ddb.query.return_value = {"Items": []}
            resp = handler(_exec_event("ci_runner"), None)
        assert resp["statusCode"] == 200, resp["body"]
        execution_item = ddb.put_item.call_args_list[0][1]["Item"]
        assert execution_item["test_platform"]["S"] == "electron"
        assert execution_item["trigger_type"]["S"] == "ci_runner"
        # Optional bundle id travels to the execution record for the runner check.
        assert execution_item["bundle_id"]["S"] == "com.productharness.desktop"
        assert "app_identifier" not in execution_item

    def test_ci_runner_without_bundle_id_omits_attribute(self):
        from execute_usecase import handler

        item = {"Item": {k: v for k, v in ELECTRON_ITEM["Item"].items() if k != "bundle_id"}}
        with patch("execute_usecase.dynamodb") as ddb, patch("execute_usecase.eventbridge"):
            ddb.get_item.return_value = item
            ddb.query.return_value = {"Items": []}
            resp = handler(_exec_event("ci_runner"), None)
        assert resp["statusCode"] == 200
        assert "bundle_id" not in ddb.put_item.call_args_list[0][1]["Item"]


# ---------------------------------------------------------------------------
# execute_test_suite
# ---------------------------------------------------------------------------


def _suite_event(trigger):
    return make_event("editor_a", path={"suite_id": "s-1"}, body={"trigger_type": trigger},
                      scopes="api/suite.write api/executions.write")


def _suite_item():
    return {"id": {"S": "s-1"}, "name": {"S": "Suite"}, "description": {"S": ""},
            "scope": {"S": "suite:s-1"}, "total_usecases": {"N": "2"}}


def _definition(platform):
    item = {
        "name": {"S": f"UC {platform}"}, "starting_url": {"S": "https://example.com"},
        "executing_region": {"S": "eu-central-1"}, "model_id": {"S": "nova-act-v1.0"},
        "test_platform": {"S": platform},
    }
    if platform == "electron":
        item["bundle_id"] = {"S": "com.productharness.desktop"}
    return {"Item": item}


class TestExecuteTestSuiteElectron:
    @pytest.mark.parametrize("trigger", ["OnDemand", "scheduled"])
    def test_mixed_suite_rejected_naming_electron_usecases(self, trigger):
        from execute_test_suite import handler

        with patch("execute_test_suite.dynamodb") as ddb, \
                patch("execute_test_suite.lambda_client") as lam, \
                patch("execute_test_suite.os.environ.get",
                      side_effect=lambda k, d=None: {"TABLE_NAME": "t", "DEFAULT_REGION": "eu-central-1"}.get(k, d)):
            ddb.get_item.side_effect = [
                {"Item": _suite_item()},
                _definition("web"),        # usecase-1 definition
                _definition("electron"),   # usecase-2 definition
            ]
            ddb.query.side_effect = [{"Items": [
                {"usecase_id": {"S": "usecase-1"}, "usecase_name": {"S": "Web"}},
                {"usecase_id": {"S": "usecase-2"}, "usecase_name": {"S": "Desktop"}},
            ]}]
            resp = handler(_suite_event(trigger), None)
        assert resp["statusCode"] == 400, resp["body"]
        body = json.loads(resp["body"])
        assert body["error"] == ELECTRON_CI_RUNNER_ONLY_ERROR
        assert body["details"]["usecase_ids"] == ["usecase-2"]
        # Nothing written, nothing launched.
        ddb.put_item.assert_not_called()
        ddb.update_item.assert_not_called()
        lam.invoke.assert_not_called()

    def test_ci_runner_suite_with_electron_creates_records(self):
        from execute_test_suite import handler

        with patch("execute_test_suite.dynamodb") as ddb, \
                patch("execute_test_suite.lambda_client") as lam, \
                patch("execute_test_suite.os.environ.get",
                      side_effect=lambda k, d=None: {"TABLE_NAME": "t", "DEFAULT_REGION": "eu-central-1"}.get(k, d)):
            ddb.get_item.side_effect = [
                {"Item": _suite_item()},
                _definition("electron"),  # definition (prefetched)
                {},                        # variables
                {},                        # hooks
                {},                        # headers
            ]
            ddb.query.side_effect = [
                {"Items": [{"usecase_id": {"S": "usecase-1"}, "usecase_name": {"S": "Desktop"}}]},
                {"Items": []},  # steps
            ]
            ddb.put_item.return_value = {}
            ddb.update_item.return_value = {}
            resp = handler(_suite_event("ci_runner"), None)
        assert resp["statusCode"] == 200, resp["body"]
        lam.invoke.assert_not_called()
        execution_items = [c[1]["Item"] for c in ddb.put_item.call_args_list
                           if c[1]["Item"]["sk"]["S"].startswith("EXECUTION#")]
        electron_items = [i for i in execution_items if i.get("test_platform", {}).get("S") == "electron"]
        assert electron_items
        assert electron_items[0]["bundle_id"]["S"] == "com.productharness.desktop"
