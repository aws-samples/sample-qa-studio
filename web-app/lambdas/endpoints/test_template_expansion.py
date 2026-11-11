"""``template_expansion`` — the one place a template is turned into use-case steps.

Used by ``import_template`` (insert into an existing use case) and
``import_usecase`` (expand ``template`` placeholders in an export JSON).
"""
import os
from decimal import Decimal

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

from fake_table import FakeTable  # noqa: E402
from template_expansion import (  # noqa: E402
    TemplateBundle,
    build_linked_steps,
    load_template_bundle,
    merge_variables,
    splice_and_renumber,
    template_secret_keys,
)

TEMPLATE = {"pk": "TEMPLATES", "sk": "TEMPLATE#t1", "id": "t1", "name": "Login", "version": Decimal(3)}
TEMPLATE_STEPS = [
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts2", "id": "ts2", "sort": Decimal(2), "step_type": "secret",
     "instruction": "Click into the password field.", "secret_key": "password"},
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts1", "id": "ts1", "sort": Decimal(1), "step_type": "browser",
     "instruction": "Open login", "browser_action": "navigate", "browser_args": '{"url": "https://e.test"}',
     "trajectory_s3_key": "never-copied"},
    {"pk": "TEMPLATE#t1", "sk": "STEP#ts3", "id": "ts3", "sort": Decimal(3), "step_type": "secret",
     "instruction": "Click into the password confirmation field.", "secret_key": "password"},
]
VARIABLES = {"pk": "TEMPLATE#t1", "sk": "VARIABLES",
             "variables": [{"key": "base", "value": "https://e.test"}, {"key": "user", "value": "qa"}]}


def _bundle(**overrides):
    data = {"metadata": TEMPLATE, "steps": sorted(TEMPLATE_STEPS, key=lambda s: s["sort"]),
            "variables": VARIABLES["variables"]}
    data.update(overrides)
    return TemplateBundle(**data)


class TestLoadTemplateBundle:
    def test_loads_metadata_sorted_steps_and_variables(self):
        table = FakeTable([TEMPLATE, *TEMPLATE_STEPS, VARIABLES])
        bundle = load_template_bundle(table, "t1")
        assert bundle is not None
        assert bundle.template_id == "t1"
        assert bundle.version == 3
        assert [s["id"] for s in bundle.steps] == ["ts1", "ts2", "ts3"]
        assert bundle.variables == VARIABLES["variables"]

    def test_missing_metadata_returns_none(self):
        table = FakeTable(TEMPLATE_STEPS)
        assert load_template_bundle(table, "t1") is None

    def test_missing_variables_record_is_empty_list(self):
        bundle = load_template_bundle(FakeTable([TEMPLATE, *TEMPLATE_STEPS]), "t1")
        assert bundle.variables == []

    def test_uses_query_not_scan(self):
        source = open(os.path.join(os.path.dirname(__file__), "template_expansion.py")).read()
        assert ".scan(" not in source


class TestBuildLinkedSteps:
    def test_linked_steps_have_fresh_ids_fields_and_linkage(self):
        steps = build_linked_steps(_bundle(), "uc-1", first_sort=5, now="2025-01-01T00:00:00Z")
        assert [s["sort"] for s in steps] == [5, 6, 7]
        assert [s["template_step_id"] for s in steps] == ["ts1", "ts2", "ts3"]
        for step in steps:
            assert step["pk"] == "USECASE#uc-1"
            assert step["sk"] == f"STEP#{step['id']}"
            assert step["template_id"] == "t1"
            assert step["template_version"] == 3
            assert step["created_at"] == "2025-01-01T00:00:00Z"
            assert "trajectory_s3_key" not in step
        assert steps[0]["browser_action"] == "navigate"
        assert steps[1]["secret_key"] == "password"
        assert len({s["id"] for s in steps}) == 3

    def test_two_expansions_get_independent_ids(self):
        first = build_linked_steps(_bundle(), "uc-1", 1, "now")
        second = build_linked_steps(_bundle(), "uc-1", 1, "now")
        assert {s["id"] for s in first}.isdisjoint({s["id"] for s in second})


class TestMergeVariables:
    def test_existing_keys_win_and_order_is_preserved(self):
        existing = [{"key": "base", "value": "https://prod"}, {"key": "x", "value": "1"}]
        incoming = [{"key": "user", "value": "qa"}, {"key": "base", "value": "https://e.test"}]
        assert merge_variables(existing, incoming) == [
            {"key": "base", "value": "https://prod"}, {"key": "x", "value": "1"}, {"key": "user", "value": "qa"},
        ]

    def test_does_not_mutate_inputs(self):
        existing = [{"key": "a", "value": "1"}]
        incoming = [{"key": "b", "value": "2"}]
        merge_variables(existing, incoming)
        assert existing == [{"key": "a", "value": "1"}]

    def test_empty_inputs(self):
        assert merge_variables([], []) == []
        assert merge_variables([], [{"key": "a", "value": "1"}]) == [{"key": "a", "value": "1"}]


class TestTemplateSecretKeys:
    def test_distinct_keys_in_step_order(self):
        assert template_secret_keys(_bundle()) == ["password"]

    def test_no_secret_steps(self):
        bundle = _bundle(steps=[TEMPLATE_STEPS[1]])
        assert template_secret_keys(bundle) == []


def _existing(*sorts):
    return [{"pk": "USECASE#uc-1", "sk": f"STEP#e{s}", "id": f"e{s}", "sort": Decimal(s)} for s in sorts]


def _new(count):
    return [{"pk": "USECASE#uc-1", "sk": f"STEP#n{i}", "id": f"n{i}", "sort": 0} for i in range(count)]


class TestSpliceAndRenumber:
    def test_insert_at_start(self):
        existing, new = _existing(1, 2), _new(2)
        changed = splice_and_renumber(existing, new, position=1)
        assert [s["sort"] for s in new] == [1, 2]
        assert [(s["id"], s["sort"]) for s in existing] == [("e1", 3), ("e2", 4)]
        assert [s["id"] for s in changed] == ["e1", "e2"]

    def test_insert_in_middle(self):
        existing, new = _existing(1, 2, 3), _new(1)
        changed = splice_and_renumber(existing, new, position=2)
        assert new[0]["sort"] == 2
        assert [(s["id"], s["sort"]) for s in existing] == [("e1", 1), ("e2", 3), ("e3", 4)]
        assert [s["id"] for s in changed] == ["e2", "e3"]

    def test_append(self):
        existing, new = _existing(1, 2), _new(2)
        changed = splice_and_renumber(existing, new, position=3)
        assert [s["sort"] for s in new] == [3, 4]
        assert changed == []

    def test_gaps_in_existing_sorts_become_contiguous(self):
        existing, new = _existing(1, 4, 9), _new(1)
        changed = splice_and_renumber(existing, new, position=2)
        assert new[0]["sort"] == 2
        assert [(s["id"], s["sort"]) for s in existing] == [("e1", 1), ("e4", 3), ("e9", 4)]
        assert [s["id"] for s in changed] == ["e4", "e9"]

    def test_unchanged_steps_are_not_reported(self):
        existing, new = _existing(1, 2, 3), _new(1)
        changed = splice_and_renumber(existing, new, position=4)
        assert changed == []
        assert [int(s["sort"]) for s in existing] == [1, 2, 3]

    def test_into_empty_usecase(self):
        new = _new(3)
        assert splice_and_renumber([], new, position=1) == []
        assert [s["sort"] for s in new] == [1, 2, 3]

    @pytest.mark.parametrize("position", [0, 5])
    def test_out_of_range_position_raises(self, position):
        with pytest.raises(ValueError):
            splice_and_renumber(_existing(1, 2, 3), _new(1), position=position)
