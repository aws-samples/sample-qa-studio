"""Tests for the shared execution-step builder (``execution_steps.py``).

``execute_usecase`` and ``execute_test_suite`` both copy STEP# records into
EXECUTION_STEP# records.  This module is the single home of that logic;
these tests pin the copied-field contract, sort preservation and the
batch-write behaviour.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")

from execution_steps import (  # noqa: E402
    COPIED_STEP_FIELDS,
    REPEAT_EXPANSION_FIELDS,
    DatasetNotFoundError,
    RepeatExpansionError,
    build_execution_step_items,
    write_execution_step_items,
)


def _step(step_id: str, sort: int, **extra) -> dict:
    item = {
        "id": {"S": step_id},
        "sort": {"N": str(sort)},
        "instruction": {"S": f"Step {step_id}"},
        "step_type": {"S": "navigation"},
    }
    item.update(extra)
    return item


class TestBuildExecutionStepItems:
    def test_keys_and_required_fields(self):
        items = build_execution_step_items([_step("s1", 1)], "exec-1", "2026-01-01T00:00:00Z")
        assert len(items) == 1
        item = items[0]
        assert item["pk"] == {"S": "EXECUTION#exec-1"}
        assert item["sk"]["S"].startswith("EXECUTION_STEP#")
        assert item["created_at"] == {"S": "2026-01-01T00:00:00Z"}
        assert item["step_id"] == {"S": "s1"}
        assert item["sort"] == {"N": "1"}
        assert item["instruction"] == {"S": "Step s1"}
        assert item["step_type"] == {"S": "navigation"}

    def test_optional_fields_copied_only_when_present(self):
        extra = {
            "cached_steps": {"S": "[]"},
            "network_url_pattern": {"S": "**/api"},
            "transform_args": {"M": {"a": {"S": "b"}}},
        }
        items = build_execution_step_items(
            [_step("s1", 1, **extra), _step("s2", 2)], "exec-1", "now",
        )
        assert items[0]["cached_steps"] == {"S": "[]"}
        assert items[0]["network_url_pattern"] == {"S": "**/api"}
        assert items[0]["transform_args"] == {"M": {"a": {"S": "b"}}}
        for field in COPIED_STEP_FIELDS:
            assert field not in items[1]

    def test_unknown_fields_are_not_copied(self):
        items = build_execution_step_items(
            [_step("s1", 1, pk={"S": "USECASE#x"}, sk={"S": "STEP#s1"}, mystery={"S": "?"})],
            "exec-1", "now",
        )
        assert items[0]["pk"] == {"S": "EXECUTION#exec-1"}
        assert items[0]["sk"]["S"].startswith("EXECUTION_STEP#")
        assert "mystery" not in items[0]

    def test_sort_order_preserved_from_input(self):
        steps = [_step("s3", 3), _step("s1", 1), _step("s2", 2)]
        items = build_execution_step_items(steps, "exec-1", "now")
        assert [i["sort"]["N"] for i in items] == ["1", "2", "3"]
        assert [i["step_id"]["S"] for i in items] == ["s1", "s2", "s3"]

    def test_each_item_gets_unique_sk(self):
        items = build_execution_step_items([_step("s1", 1), _step("s2", 2)], "exec-1", "now")
        assert items[0]["sk"] != items[1]["sk"]

    def test_copied_field_list_matches_legacy_contract(self):
        """The list that used to live in both execute Lambdas, verbatim."""
        assert set(COPIED_STEP_FIELDS) >= {
            "secret_key", "validation_type", "validation_operator", "validation_value",
            "capture_variable", "assertion_variable", "value_type", "value_format",
            "enable_advanced_click_types", "value_source", "cached_steps",
            "cache_last_updated", "trajectory_s3_key", "trajectory_last_updated",
            "browser_action", "browser_args", "transform_operation", "transform_args",
            "network_url_pattern", "network_method", "network_request_body",
            "network_body_match_type", "network_mock_response", "network_mock_passthrough",
            "network_timeout", "network_response_body", "network_response_body_match_type",
            "network_response_status",
        }


class TestWriteExecutionStepItems:
    def test_no_items_no_calls(self):
        dynamodb = MagicMock()
        write_execution_step_items(dynamodb, "tbl", [])
        dynamodb.batch_write_item.assert_not_called()

    def test_batches_of_25(self):
        dynamodb = MagicMock()
        dynamodb.batch_write_item.return_value = {"UnprocessedItems": {}}
        items = build_execution_step_items(
            [_step(f"s{i}", i) for i in range(1, 61)], "exec-1", "now",
        )
        write_execution_step_items(dynamodb, "tbl", items)
        sizes = [
            len(c.kwargs["RequestItems"]["tbl"])
            for c in dynamodb.batch_write_item.call_args_list
        ]
        assert sizes == [25, 25, 10]
        written = [
            r["PutRequest"]["Item"]
            for c in dynamodb.batch_write_item.call_args_list
            for r in c.kwargs["RequestItems"]["tbl"]
        ]
        assert written == items

    def test_unprocessed_items_are_retried(self):
        dynamodb = MagicMock()
        items = build_execution_step_items([_step("s1", 1), _step("s2", 2)], "exec-1", "now")
        leftover = {"tbl": [{"PutRequest": {"Item": items[1]}}]}
        dynamodb.batch_write_item.side_effect = [
            {"UnprocessedItems": leftover},
            {"UnprocessedItems": {}},
        ]
        with patch("execution_steps.time.sleep"):
            write_execution_step_items(dynamodb, "tbl", items)
        assert dynamodb.batch_write_item.call_count == 2
        second = dynamodb.batch_write_item.call_args_list[1].kwargs["RequestItems"]
        assert second == leftover

    def test_gives_up_after_max_retries(self):
        dynamodb = MagicMock()
        items = build_execution_step_items([_step("s1", 1)], "exec-1", "now")
        dynamodb.batch_write_item.return_value = {
            "UnprocessedItems": {"tbl": [{"PutRequest": {"Item": items[0]}}]}
        }
        with patch("execution_steps.time.sleep"), pytest.raises(RuntimeError):
            write_execution_step_items(dynamodb, "tbl", items)


def _repeat_step(step_id, sort, label, columns, rows):
    return {
        "id": {"S": step_id},
        "sort": {"N": str(sort)},
        "instruction": {"S": label},
        "step_type": {"S": "repeat"},
        "repeat_columns": {"L": [{"S": c} for c in columns]},
        "repeat_rows": {"L": [{"L": [{"S": cell} for cell in row]} for row in rows]},
    }


def _child_step(step_id, sort, parent, **extra):
    return _step(step_id, sort, parent_step_id={"S": parent}, **extra)


class TestBuildWithRepeatExpansion:
    def test_no_repeat_keeps_original_sort_values(self):
        """Non-repeat usecases must be byte-identical to the pre-repeat builder."""
        items = build_execution_step_items([_step("s1", 0), _step("s2", 1)], "exec-1", "now")
        assert [i["sort"] for i in items] == [{"N": "0"}, {"N": "1"}]

    def test_repeat_unrolled_into_typed_items(self):
        steps = [
            _repeat_step("r1", 1, "Users", ["email"], [["a@x.test"], ["b@x.test"]]),
            _child_step("c1", 2, "r1", trajectory_s3_key={"S": "k"}, cached_steps={"S": "[]"}),
            _step("p1", 3),
        ]
        items = build_execution_step_items(steps, "exec-1", "now")
        assert [i["step_id"]["S"] for i in items] == ["c1", "c1", "p1"]
        assert [i["sort"]["N"] for i in items] == ["1", "2", "3"]
        first = items[0]
        assert first["repeat_step_id"] == {"S": "r1"}
        assert first["repeat_label"] == {"S": "Users"}
        assert first["repeat_row_index"] == {"N": "1"}
        assert first["repeat_row_total"] == {"N": "2"}
        assert first["row_variables"] == {"M": {
            "email": {"S": "a@x.test"}, "RepeatIndex": {"S": "1"}, "RepeatTotal": {"S": "2"},
        }}
        assert "trajectory_s3_key" not in first
        assert "cached_steps" not in first
        assert "parent_step_id" not in first
        assert items[1]["row_variables"]["M"]["email"] == {"S": "b@x.test"}
        for field in REPEAT_EXPANSION_FIELDS:
            assert field not in items[2]

    def test_dataset_override_replaces_rows(self):
        steps = [
            _repeat_step("r1", 1, "Users", ["email"], [["stored"]]),
            _child_step("c1", 2, "r1"),
        ]
        items = build_execution_step_items(
            steps, "exec-1", "now", {"Users": {"columns": ["email"], "rows": [["o1"], ["o2"], ["o3"]]}},
        )
        assert [i["row_variables"]["M"]["email"]["S"] for i in items] == ["o1", "o2", "o3"]

    def test_expansion_error_propagates(self):
        steps = [_repeat_step("r1", 1, "Users", ["email"], [["a"]])]  # no children
        with pytest.raises(RepeatExpansionError):
            build_execution_step_items(steps, "exec-1", "now")


def _dataset_repeat_step(step_id, sort, label, dataset_id):
    return {
        "id": {"S": step_id},
        "sort": {"N": str(sort)},
        "instruction": {"S": label},
        "step_type": {"S": "repeat"},
        "dataset_id": {"S": dataset_id},
    }


def _without_sk(items):
    """Items minus their fresh UUIDv7 ``sk`` so two builds can be compared."""
    return [{k: v for k, v in item.items() if k != "sk"} for item in items]


class TestBuildWithDatasetReferences:
    """``dataset_id`` repeats are resolved through ``dataset_fetcher`` before expansion."""

    _DATASETS = {
        "ds-1": {"columns": ["email"], "rows": [["a@x.test"], ["b@x.test"]]},
    }

    def test_dataset_reference_is_resolved_and_expanded(self):
        fetcher = MagicMock(side_effect=self._DATASETS.get)
        steps = [
            _dataset_repeat_step("r1", 1, "Users", "ds-1"),
            _child_step("c1", 2, "r1"),
            _step("p1", 3),
        ]
        items = build_execution_step_items(steps, "exec-1", "now", dataset_fetcher=fetcher)
        assert [i["step_id"]["S"] for i in items] == ["c1", "c1", "p1"]
        assert [i["row_variables"]["M"]["email"]["S"] for i in items[:2]] == ["a@x.test", "b@x.test"]
        assert items[0]["repeat_label"] == {"S": "Users"}
        assert items[0]["repeat_row_total"] == {"N": "2"}
        fetcher.assert_called_once_with("ds-1")
        for item in items:
            assert "dataset_id" not in item
            assert "repeat_columns" not in item
            assert "repeat_rows" not in item

    def test_missing_dataset_raises_before_expansion(self):
        steps = [_dataset_repeat_step("r1", 1, "Users", "ds-missing"), _child_step("c1", 2, "r1")]
        with pytest.raises(DatasetNotFoundError) as excinfo:
            build_execution_step_items(steps, "exec-1", "now", dataset_fetcher=lambda _id: None)
        assert excinfo.value.dataset_id == "ds-missing"

    def test_without_fetcher_a_reference_is_unresolvable(self):
        steps = [_dataset_repeat_step("r1", 1, "Users", "ds-1"), _child_step("c1", 2, "r1")]
        with pytest.raises(DatasetNotFoundError) as excinfo:
            build_execution_step_items(steps, "exec-1", "now")
        assert excinfo.value.dataset_id == "ds-1"

    def test_dataset_override_wins_over_application_dataset(self):
        fetcher = MagicMock(side_effect=self._DATASETS.get)
        steps = [_dataset_repeat_step("r1", 1, "Users", "ds-1"), _child_step("c1", 2, "r1")]
        items = build_execution_step_items(
            steps, "exec-1", "now",
            dataset_overrides={"Users": {"columns": ["email"], "rows": [["o1"], ["o2"], ["o3"]]}},
            dataset_fetcher=fetcher,
        )
        assert [i["row_variables"]["M"]["email"]["S"] for i in items] == ["o1", "o2", "o3"]
        fetcher.assert_called_once_with("ds-1")

    def test_override_columns_must_match_the_application_dataset(self):
        steps = [_dataset_repeat_step("r1", 1, "Users", "ds-1"), _child_step("c1", 2, "r1")]
        with pytest.raises(RepeatExpansionError, match="do not match"):
            build_execution_step_items(
                steps, "exec-1", "now",
                dataset_overrides={"Users": {"columns": ["other"], "rows": [["o1"]]}},
                dataset_fetcher=self._DATASETS.get,
            )

    def test_inline_repeat_never_calls_the_fetcher(self):
        fetcher = MagicMock()
        steps = [_repeat_step("r1", 1, "Users", ["email"], [["a"]]), _child_step("c1", 2, "r1")]
        build_execution_step_items(steps, "exec-1", "now", dataset_fetcher=fetcher)
        fetcher.assert_not_called()

    def test_usecase_without_repeat_is_byte_identical_with_a_fetcher(self):
        fetcher = MagicMock()
        steps = [_step("s1", 0, cached_steps={"S": "[]"}), _step("s2", 1)]
        with_fetcher = build_execution_step_items(steps, "exec-1", "now", dataset_fetcher=fetcher)
        without = build_execution_step_items(steps, "exec-1", "now")
        assert _without_sk(with_fetcher) == _without_sk(without)
        assert [i["sort"] for i in with_fetcher] == [{"N": "0"}, {"N": "1"}]
        fetcher.assert_not_called()
