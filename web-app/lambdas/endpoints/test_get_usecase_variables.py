"""GET /usecase/{id}/variables returns the *effective* list.

Application ``VARIABLES`` rows (inherited, ``source: "application"``) come
first sorted by key, then the use case's own rows in stored order
(``source: "usecase"``); a use-case key shadows the application key. The
application id comes from the owner lookup (``get_usecase_owner``), not from
a query.
"""
import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

import get_usecase_variables  # noqa: E402
from authz_test_support import APP_ID, UC_ID, make_event, resource_access_granted, worker_header  # noqa: E402
from fake_table import FakeTable  # noqa: E402

USECASE = {"pk": "USECASES", "sk": f"USECASE#{UC_ID}", "id": UC_ID, "application_id": APP_ID,
           "owner_team_id": "team-a"}
LEGACY_USECASE = {"pk": "USECASES", "sk": f"USECASE#{UC_ID}", "id": UC_ID}
APP_KEY = {"pk": f"APPLICATION#{APP_ID}", "sk": "VARIABLES"}
UC_KEY = {"pk": f"USECASE#{UC_ID}", "sk": "USECASE_VARIABLES"}


def _rows(*pairs):
    return [{"key": k, "value": v} for k, v in pairs]


class _RecordingTable(FakeTable):
    def __init__(self, items=()):
        super().__init__(items)
        self.read_keys = []

    def get_item(self, Key, **kwargs):  # noqa: N803
        self.read_keys.append((Key["pk"], Key["sk"]))
        return super().get_item(Key, **kwargs)


@pytest.fixture(autouse=True)
def _access_granted():
    with resource_access_granted():
        yield


def _run(table, caller="viewer_a", **event_kwargs):
    with patch.object(get_usecase_variables, "boto3") as boto_mock, \
            patch("permissions_repo._get_table", return_value=table):
        boto_mock.resource.return_value.Table.return_value = table
        response = get_usecase_variables.handler(make_event(caller, path={"id": UC_ID}, **event_kwargs), None)
    assert response["statusCode"] == 200, response["body"]
    return json.loads(response["body"])["variables"]


class TestEffectiveVariables:
    def test_nothing_stored_is_empty(self):
        assert _run(_RecordingTable([USECASE])) == []

    def test_application_rows_first_sorted_then_usecase_rows_in_stored_order(self):
        table = _RecordingTable([
            USECASE,
            {**APP_KEY, "variables": _rows(("zone", "eu"), ("base", "https://app"))},
            {**UC_KEY, "variables": _rows(("user", "qa"), ("env", "stage"))},
        ])
        assert _run(table) == [
            {"key": "base", "value": "https://app", "source": "application"},
            {"key": "zone", "value": "eu", "source": "application"},
            {"key": "user", "value": "qa", "source": "usecase"},
            {"key": "env", "value": "stage", "source": "usecase"},
        ]

    def test_usecase_key_shadows_application_key(self):
        table = _RecordingTable([
            USECASE,
            {**APP_KEY, "variables": _rows(("base", "https://app"), ("zone", "eu"))},
            {**UC_KEY, "variables": _rows(("base", "https://uc"))},
        ])
        assert _run(table) == [
            {"key": "zone", "value": "eu", "source": "application"},
            {"key": "base", "value": "https://uc", "source": "usecase"},
        ]

    def test_application_only(self):
        table = _RecordingTable([USECASE, {**APP_KEY, "variables": _rows(("a", "1"))}])
        assert _run(table) == [{"key": "a", "value": "1", "source": "application"}]

    def test_reads_are_get_items_only(self):
        table = _RecordingTable([USECASE, {**APP_KEY, "variables": []}, {**UC_KEY, "variables": []}])
        _run(table)
        assert (APP_KEY["pk"], APP_KEY["sk"]) in table.read_keys
        assert (UC_KEY["pk"], UC_KEY["sk"]) in table.read_keys
        assert ("USECASES", f"USECASE#{UC_ID}") in table.read_keys  # owner lookup
        assert len(table.read_keys) == 3


class TestLegacyUsecaseWithoutApplication:
    """No ``application_id`` → use-case layer only, in stored order, exactly as before."""

    STORED = _rows(("b", "2"), ("a", "1"), ("empty", ""))

    def test_rows_identical_to_previous_output_plus_source(self):
        table = _RecordingTable([LEGACY_USECASE, {**UC_KEY, "variables": self.STORED}])
        rows = _run(table)
        assert [{"key": r["key"], "value": r["value"]} for r in rows] == self.STORED
        assert {r["source"] for r in rows} == {"usecase"}

    def test_legacy_capitalised_rows_are_normalised(self):
        table = _RecordingTable([LEGACY_USECASE, {**UC_KEY, "variables": [{"Key": "A", "Value": "1"}]}])
        assert _run(table) == [{"key": "A", "value": "1", "source": "usecase"}]

    def test_no_application_record_is_read(self):
        table = _RecordingTable([LEGACY_USECASE, {**UC_KEY, "variables": self.STORED}])
        _run(table)
        assert not any(pk.startswith("APPLICATION#") for pk, _ in table.read_keys)

    def test_empty_when_no_variables_record(self):
        assert _run(_RecordingTable([LEGACY_USECASE])) == []


def test_worker_is_allowed():
    table = _RecordingTable([USECASE, {**UC_KEY, "variables": _rows(("a", "1"))}])
    rows = _run(table, caller="worker", worker_header=worker_header())
    assert rows == [{"key": "a", "value": "1", "source": "usecase"}]


def test_table_error_is_500():
    class _Broken(FakeTable):
        def get_item(self, Key, **_):  # noqa: N803
            raise RuntimeError("boom")

    with patch.object(get_usecase_variables, "boto3") as boto_mock, \
            patch("permissions_repo._get_table", return_value=FakeTable([USECASE])):
        boto_mock.resource.return_value.Table.return_value = _Broken()
        response = get_usecase_variables.handler(make_event("viewer_a", path={"id": UC_ID}), None)
    assert response["statusCode"] == 500
    assert json.loads(response["body"]) == {"error": "Internal server error"}
