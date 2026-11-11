"""``dataset_usage.find_dataset_references`` — which use cases of an application reference a dataset.

Walks ``APPLICATION#{id} / USECASE#*`` → ``USECASE#{uid} / STEP#*`` and filters
on ``dataset_id``; no scan, no GSI.  Used by ``DELETE …/datasets/{id}`` (409
body) and later by ``associate_usecases``.
"""
import os

os.environ.setdefault("TABLE_NAME", "test-table")

from dataset_usage import find_dataset_references, find_usecase_dataset_steps  # noqa: E402
from fake_table import FakeTable  # noqa: E402

APP = "app-1"


def _assoc(usecase_id, app_id=APP):
    return {"pk": f"APPLICATION#{app_id}", "sk": f"USECASE#{usecase_id}", "associated_at": "t"}


def _usecase(usecase_id, name):
    return {"pk": "USECASES", "sk": f"USECASE#{usecase_id}", "id": usecase_id, "name": name}


def _step(usecase_id, step_id, step_type="repeat", **extra):
    item = {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}", "id": step_id, "sort": 1,
            "step_type": step_type, "instruction": "x"}
    item.update(extra)
    return item


class _CountingTable(FakeTable):
    def __init__(self, items):
        super().__init__(items)
        self.queries = []
        self.gets = []

    def query(self, KeyConditionExpression, **kw):  # noqa: N803
        self.queries.append(KeyConditionExpression)
        return super().query(KeyConditionExpression, **kw)

    def get_item(self, Key, **kw):  # noqa: N803
        self.gets.append(dict(Key))
        return super().get_item(Key, **kw)


def _table():
    return _CountingTable([
        _assoc("uc-1"), _assoc("uc-2"), _assoc("uc-3"), _assoc("uc-other", app_id="app-2"),
        _usecase("uc-1", "Login"), _usecase("uc-2", "Checkout"), _usecase("uc-3", "Search"),
        _usecase("uc-other", "Other app"),
        {"pk": f"APPLICATION#{APP}", "sk": "METADATA", "name": "App"},
        {"pk": f"APPLICATION#{APP}", "sk": "DATASET#ds-1", "dataset_id": "ds-1", "name": "customers"},
        _step("uc-1", "s1", dataset_id="ds-1"),
        _step("uc-1", "s2", dataset_id="ds-1"),            # two refs in one use case → listed once
        _step("uc-2", "s3", repeat_columns=["a"], repeat_rows=[["1"]]),  # inline repeat
        _step("uc-2", "s4", step_type="navigation", parent_step_id="s3"),
        _step("uc-3", "s5", dataset_id="ds-2"),            # another dataset
        _step("uc-other", "s6", dataset_id="ds-1"),        # another application
    ])


class TestFindDatasetReferences:
    def test_lists_each_referencing_usecase_once_with_its_name(self):
        assert find_dataset_references(_table(), APP, "ds-1") == [{"usecase_id": "uc-1", "name": "Login"}]

    def test_other_dataset(self):
        assert find_dataset_references(_table(), APP, "ds-2") == [{"usecase_id": "uc-3", "name": "Search"}]

    def test_unreferenced_dataset(self):
        assert find_dataset_references(_table(), APP, "ds-none") == []

    def test_application_without_usecases(self):
        table = _CountingTable([{"pk": "APPLICATION#empty", "sk": "METADATA"}])
        assert find_dataset_references(table, "empty", "ds-1") == []
        assert len(table.queries) == 1

    def test_only_queries_and_bounded_gets(self):
        table = _table()
        find_dataset_references(table, APP, "ds-1")
        # 1 association query + 1 step query per use case of the application.
        assert len(table.queries) == 1 + 3
        # Name lookups only for the referencing use cases.
        assert table.gets == [{"pk": "USECASES", "sk": "USECASE#uc-1"}]

    def test_missing_usecase_record_falls_back_to_id(self):
        table = _CountingTable([_assoc("uc-ghost"), _step("uc-ghost", "s1", dataset_id="ds-1")])
        assert find_dataset_references(table, APP, "ds-1") == [{"usecase_id": "uc-ghost", "name": "uc-ghost"}]

    def test_results_sorted_by_name(self):
        table = _CountingTable([
            _assoc("uc-b"), _assoc("uc-a"), _usecase("uc-b", "Zeta"), _usecase("uc-a", "Alpha"),
            _step("uc-b", "s1", dataset_id="ds-1"), _step("uc-a", "s2", dataset_id="ds-1"),
        ])
        assert [r["name"] for r in find_dataset_references(table, APP, "ds-1")] == ["Alpha", "Zeta"]


class TestFindUsecaseDatasetSteps:
    def test_lists_referencing_steps_in_sort_order_with_usecase_name(self):
        table = _CountingTable([
            _usecase("uc-1", "Login"),
            _step("uc-1", "s2", dataset_id="ds-b", sort=3, instruction="second"),
            _step("uc-1", "s1", dataset_id="ds-a", sort=1, instruction="first"),
            _step("uc-1", "s3", repeat_columns=["a"], repeat_rows=[["1"]], sort=2),
            _step("uc-1", "s4", step_type="navigation", parent_step_id="s3", sort=4),
            _step("uc-1", "s5", dataset_id="", sort=5),
        ])
        assert find_usecase_dataset_steps(table, "uc-1") == {
            "usecase_id": "uc-1", "name": "Login",
            "steps": [{"id": "s1", "instruction": "first"}, {"id": "s2", "instruction": "second"}],
        }
        assert len(table.queries) == 1
        assert table.gets == [{"pk": "USECASES", "sk": "USECASE#uc-1"}]

    def test_none_without_references_and_no_name_lookup(self):
        table = _CountingTable([
            _usecase("uc-2", "Checkout"),
            _step("uc-2", "s3", repeat_columns=["a"], repeat_rows=[["1"]]),
        ])
        assert find_usecase_dataset_steps(table, "uc-2") is None
        assert table.gets == []

    def test_none_for_unknown_usecase(self):
        assert find_usecase_dataset_steps(_CountingTable([]), "uc-missing") is None

    def test_missing_usecase_record_falls_back_to_id(self):
        table = _CountingTable([_step("uc-ghost", "s1", dataset_id="ds-1")])
        assert find_usecase_dataset_steps(table, "uc-ghost")["name"] == "uc-ghost"
