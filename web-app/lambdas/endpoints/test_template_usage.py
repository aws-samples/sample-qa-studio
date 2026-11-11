"""``template_usage`` — the ``TEMPLATE#{tid} / USAGE#{usecase_id}`` reverse index.

A USAGE record says "this use case has at least one step linked to this
template".  It is the only way to find linked use-case steps (no GSI covers
``template_id``), so every handler that creates or destroys linkage goes
through this module.
"""
import os

os.environ.setdefault("TABLE_NAME", "test-table")

from fake_table import FakeTable  # noqa: E402
from template_usage import (  # noqa: E402
    LINKAGE_FIELDS,
    list_usages,
    record_usage,
    remove_usage,
    remove_usage_if_unlinked,
    unlink_usecase_steps,
    usage_item,
)


def _linked(step_id, template_id="t1", usecase_id="uc-1", sort=1):
    return {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}", "id": step_id, "sort": sort,
            "instruction": "x", "step_type": "navigation", "template_id": template_id,
            "template_step_id": f"ts-{step_id}", "template_version": 3}


def _plain(step_id, usecase_id="uc-1", sort=9):
    return {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}", "id": step_id, "sort": sort,
            "instruction": "plain", "step_type": "navigation"}


class TestUsageItem:
    def test_shape(self):
        item = usage_item("t1", "uc-1", "2025-01-01T00:00:00Z")
        assert item == {"pk": "TEMPLATE#t1", "sk": "USAGE#uc-1", "template_id": "t1", "usecase_id": "uc-1",
                        "created_at": "2025-01-01T00:00:00Z"}


class TestRecordUsage:
    def test_put_is_idempotent(self):
        table = FakeTable()
        record_usage(table, "t1", "uc-1")
        record_usage(table, "t1", "uc-1")
        assert len(table.by_prefix("TEMPLATE#t1", "USAGE#")) == 1
        stored = table.get("TEMPLATE#t1", "USAGE#uc-1")
        assert stored["template_id"] == "t1" and stored["usecase_id"] == "uc-1" and stored["created_at"]


class TestListUsages:
    def test_only_usage_records_of_that_template(self):
        table = FakeTable([
            usage_item("t1", "uc-1", "now"), usage_item("t1", "uc-2", "now"), usage_item("t2", "uc-3", "now"),
            {"pk": "TEMPLATE#t1", "sk": "STEP#ts1", "id": "ts1"}, {"pk": "TEMPLATE#t1", "sk": "VARIABLES"},
        ])
        usages = list_usages(table, "t1")
        assert sorted(u["usecase_id"] for u in usages) == ["uc-1", "uc-2"]

    def test_empty(self):
        assert list_usages(FakeTable(), "t1") == []

    def test_follows_pagination(self):
        class Paged(FakeTable):
            def __init__(self):
                super().__init__()
                self.calls = []

            def query(self, KeyConditionExpression, ExclusiveStartKey=None, **_):  # noqa: N803
                self.calls.append(ExclusiveStartKey)
                if ExclusiveStartKey is None:
                    return {"Items": [usage_item("t1", "uc-1", "now")], "LastEvaluatedKey": {"pk": "TEMPLATE#t1", "sk": "USAGE#uc-1"}}
                return {"Items": [usage_item("t1", "uc-2", "now")]}

        table = Paged()
        assert [u["usecase_id"] for u in list_usages(table, "t1")] == ["uc-1", "uc-2"]
        assert table.calls == [None, {"pk": "TEMPLATE#t1", "sk": "USAGE#uc-1"}]


class TestRemoveUsage:
    def test_deletes_record(self):
        table = FakeTable([usage_item("t1", "uc-1", "now")])
        remove_usage(table, "t1", "uc-1")
        assert table.get("TEMPLATE#t1", "USAGE#uc-1") is None

    def test_absent_is_fine(self):
        remove_usage(FakeTable(), "t1", "uc-1")


class TestRemoveUsageIfUnlinked:
    def test_other_linked_steps_remain_keeps_record(self):
        table = FakeTable([usage_item("t1", "uc-1", "now"), _linked("s1"), _plain("s2")])
        assert remove_usage_if_unlinked(table, "t1", "uc-1") is False
        assert table.get("TEMPLATE#t1", "USAGE#uc-1") is not None

    def test_last_linked_step_gone_removes_record(self):
        table = FakeTable([usage_item("t1", "uc-1", "now"), _plain("s2"), _linked("s3", template_id="t2")])
        assert remove_usage_if_unlinked(table, "t1", "uc-1") is True
        assert table.get("TEMPLATE#t1", "USAGE#uc-1") is None
        # the other template's usage is not touched
        assert table.delete_calls == [{"pk": "TEMPLATE#t1", "sk": "USAGE#uc-1"}]


class TestUnlinkUsecaseSteps:
    def test_strips_linkage_from_matching_steps_only(self):
        table = FakeTable([_linked("s1"), _linked("s2", sort=2), _linked("s3", template_id="t2", sort=3), _plain("s4")])
        assert unlink_usecase_steps(table, "t1", "uc-1") == 2
        for step_id in ("s1", "s2"):
            step = table.get("USECASE#uc-1", f"STEP#{step_id}")
            for field in LINKAGE_FIELDS:
                assert field not in step
            assert step["instruction"] == "x" and step["sort"]
        other = table.get("USECASE#uc-1", "STEP#s3")
        assert other["template_id"] == "t2" and other["template_step_id"] == "ts-s3"
        assert table.get("USECASE#uc-1", "STEP#s4") == _plain("s4")
        assert len(table.update_calls) == 2

    def test_update_is_conditional_on_template_id(self):
        table = FakeTable([_linked("s1")])
        unlink_usecase_steps(table, "t1", "uc-1")
        call = table.update_calls[0]
        assert call["ConditionExpression"] == "template_id = :tid"
        assert call["ExpressionAttributeValues"] == {":tid": "t1"}
        assert call["UpdateExpression"] == "REMOVE template_id, template_step_id, template_version"

    def test_concurrent_relink_is_skipped(self):
        """A step relinked to another template between query and update is left alone."""
        class Racy(FakeTable):
            def query(self, *a, **k):
                response = super().query(*a, **k)
                self.items[("USECASE#uc-1", "STEP#s1")]["template_id"] = "t9"
                return response

        table = Racy([_linked("s1"), _linked("s2", sort=2)])
        assert unlink_usecase_steps(table, "t1", "uc-1") == 1
        assert table.get("USECASE#uc-1", "STEP#s1")["template_id"] == "t9"
        assert "template_id" not in table.get("USECASE#uc-1", "STEP#s2")

    def test_no_linked_steps(self):
        table = FakeTable([_plain("s4")])
        assert unlink_usecase_steps(table, "t1", "uc-1") == 0
        assert table.update_calls == []

    def test_fields_match_build_linked_steps(self):
        from template_expansion import TemplateBundle, build_linked_steps
        bundle = TemplateBundle(metadata={"id": "t1", "version": 1},
                                steps=[{"id": "ts1", "instruction": "x", "step_type": "navigation"}])
        linked = build_linked_steps(bundle, "uc-1", 1, "now")[0]
        assert set(LINKAGE_FIELDS) <= set(linked)
