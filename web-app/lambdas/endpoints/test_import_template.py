"""``POST /usecase/{id}/import-template`` — ordinal positioning + contiguous renumbering.

``insert_position`` contract: omitted / ``-1`` append, ``0`` → ``1`` (UI
back-compat), ``1..n+1`` = the template's first step becomes step N, anything
else ``400``.  Existing steps are renumbered ``1..n`` so gaps disappear, and
only steps whose ``sort`` actually changed are rewritten.
"""
import json
import os
from decimal import Decimal
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import import_template  # noqa: E402
from authz_test_support import resource_access_granted  # noqa: E402
from fake_table import FakeTable  # noqa: E402


@pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by the *_access tests."""
    with resource_access_granted():
        yield


TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": Decimal(2)}
TEMPLATE_STEPS = [
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts1", "id": "ts1", "sort": Decimal(1), "step_type": "browser",
     "instruction": "Open login", "browser_action": "navigate", "browser_args": '{"url": "https://e.test"}'},
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts2", "id": "ts2", "sort": Decimal(2), "step_type": "secret",
     "instruction": "Click into the password field.", "secret_key": "password"},
]
TEMPLATE_VARIABLES = {"pk": "TEMPLATE#t1", "sk": "VARIABLES",
                      "variables": [{"key": "base", "value": "https://e.test"}, {"key": "user", "value": "qa"}]}
USECASE = {"pk": "USECASES", "sk": "USECASE#uc-1", "id": "uc-1"}
SCOPE = "api/usecases.write api/templates.read"


def _existing(*sorts):
    return [{"pk": "USECASE#uc-1", "sk": f"STEP#e{s}", "id": f"e{s}", "sort": Decimal(s), "created_at": "t0",
             "instruction": f"existing {s}", "step_type": "navigation"} for s in sorts]


def _event(body):
    return {"body": json.dumps(body), "pathParameters": {"id": "uc-1"},
            "requestContext": {"authorizer": {"sub": "u1", "email": "qa@example.com", "scope": SCOPE}}}


def _run(table, body):
    with patch.object(import_template, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        return import_template.handler(_event(body), None)


def _ordered(table):
    steps = sorted(table.by_prefix("USECASE#uc-1", "STEP#"), key=lambda s: int(s["sort"]))
    return [(int(s["sort"]), s.get("template_step_id", s["id"])) for s in steps]


class TestPositioning:
    def test_append_when_omitted(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE, *_existing(1, 2)])
        response = _run(table, {"template_id": "t1"})
        assert response["statusCode"] == 201, response["body"]
        assert _ordered(table) == [(1, "e1"), (2, "e2"), (3, "ts1"), (4, "ts2")]

    def test_append_when_minus_one(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE, *_existing(1, 2)])
        _run(table, {"template_id": "t1", "insert_position": -1})
        assert _ordered(table) == [(1, "e1"), (2, "e2"), (3, "ts1"), (4, "ts2")]

    @pytest.mark.parametrize("position", [0, 1])
    def test_insert_at_start(self, position):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE, *_existing(1, 2)])
        _run(table, {"template_id": "t1", "insert_position": position})
        assert _ordered(table) == [(1, "ts1"), (2, "ts2"), (3, "e1"), (4, "e2")]

    def test_insert_in_middle(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE, *_existing(1, 2, 3)])
        _run(table, {"template_id": "t1", "insert_position": 2})
        assert _ordered(table) == [(1, "e1"), (2, "ts1"), (3, "ts2"), (4, "e2"), (5, "e3")]

    def test_insert_at_end_explicit(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE, *_existing(1, 2)])
        _run(table, {"template_id": "t1", "insert_position": 3})
        assert _ordered(table) == [(1, "e1"), (2, "e2"), (3, "ts1"), (4, "ts2")]

    def test_gaps_become_contiguous(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE, *_existing(1, 4, 9)])
        _run(table, {"template_id": "t1", "insert_position": 2})
        assert _ordered(table) == [(1, "e1"), (2, "ts1"), (3, "ts2"), (4, "e4"), (5, "e9")]

    def test_only_changed_existing_steps_are_rewritten(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE, *_existing(1, 2, 3)])
        _run(table, {"template_id": "t1", "insert_position": 3})
        written = {item["sk"] for item in table.put_calls if item["sk"].startswith("STEP#")}
        assert "STEP#e1" not in written and "STEP#e2" not in written
        assert "STEP#e3" in written
        assert len(written) == 3

    def test_empty_usecase(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE])
        response = _run(table, {"template_id": "t1", "insert_position": 1})
        assert response["statusCode"] == 201
        assert _ordered(table) == [(1, "ts1"), (2, "ts2")]

    @pytest.mark.parametrize("position", [-2, 4, "two", 1.5])
    def test_out_of_range_is_400_and_writes_nothing(self, position):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE, *_existing(1, 2)])
        response = _run(table, {"template_id": "t1", "insert_position": position})
        assert response["statusCode"] == 400, response["body"]
        assert "insert_position" in json.loads(response["body"])["error"]
        assert table.put_calls == []


class TestLinkageAndResponse:
    def test_linkage_fields_and_response(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE])
        response = _run(table, {"template_id": "t1"})
        body = json.loads(response["body"])
        assert body["steps_created"] == 2
        assert body["missingSecrets"] == ["password"]
        for step in table.by_prefix("USECASE#uc-1", "STEP#"):
            assert step["template_id"] == "t1"
            assert step["template_version"] == 2
            assert step["template_step_id"] in ("ts1", "ts2")
            assert step["created_at"]

    def test_usage_record_written_once(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE])
        _run(table, {"template_id": "t1"})
        _run(table, {"template_id": "t1"})
        usages = table.by_prefix("TEMPLATE#t1", "USAGE#")
        assert len(usages) == 1
        assert usages[0]["sk"] == "USAGE#uc-1"
        assert usages[0]["template_id"] == "t1" and usages[0]["usecase_id"] == "uc-1" and usages[0]["created_at"]

    def test_usage_written_after_steps(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE])
        _run(table, {"template_id": "t1"})
        kinds = [item["sk"].split("#")[0] for item in table.put_calls]
        assert kinds.index("USAGE") > kinds.index("STEP")

    def test_template_not_found(self):
        table = FakeTable([USECASE])
        response = _run(table, {"template_id": "nope"})
        assert response["statusCode"] == 404
        assert table.put_calls == []

    def test_missing_template_id(self):
        response = _run(FakeTable([USECASE]), {})
        assert response["statusCode"] == 400


class TestVariables:
    def test_template_variables_merged_existing_win(self):
        usecase_vars = {"pk": "USECASE#uc-1", "sk": "USECASE_VARIABLES",
                        "variables": [{"key": "base", "value": "https://prod"}], "created_at": "t0"}
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, TEMPLATE_VARIABLES, USECASE, usecase_vars])
        _run(table, {"template_id": "t1"})
        assert table.get("USECASE#uc-1", "USECASE_VARIABLES")["variables"] == [
            {"key": "base", "value": "https://prod"}, {"key": "user", "value": "qa"},
        ]

    def test_variables_record_created_when_missing(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, TEMPLATE_VARIABLES, USECASE])
        _run(table, {"template_id": "t1"})
        record = table.get("USECASE#uc-1", "USECASE_VARIABLES")
        assert record["variables"] == TEMPLATE_VARIABLES["variables"]
        assert record["created_at"]

    def test_no_template_variables_writes_no_record(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, USECASE])
        _run(table, {"template_id": "t1"})
        assert table.get("USECASE#uc-1", "USECASE_VARIABLES") is None


class TestLogging:
    def test_no_per_step_instruction_logging(self):
        source = open(import_template.__file__).read()
        assert "instruction=" not in source
