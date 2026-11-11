"""Deploy-time backfill of ``USAGE#`` records for pre-existing linked use-case steps.

Runs once per handler-code change via a CDK ``Trigger``.  Scans the table
(the only scan in the feature), collects distinct ``(template_id,
usecase_id)`` pairs, writes idempotent USAGE records, and hands over to a
fresh invocation when it runs out of time.
"""
import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("TABLE_NAME", "test-table")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "backfill-fn")

import backfill_template_usages  # noqa: E402
from fake_table import FakeTable  # noqa: E402


def _step(usecase_id, step_id, template_id=None):
    item = {"pk": f"USECASE#{usecase_id}", "sk": f"STEP#{step_id}"}
    if template_id:
        item["template_id"] = template_id
    return item


class ScanTable(FakeTable):
    """FakeTable with a paginated ``scan`` returning the configured pages."""

    def __init__(self, pages):
        super().__init__()
        self.pages = pages
        self.scan_calls = []

    def scan(self, **kwargs):
        self.scan_calls.append(kwargs)
        index = kwargs.get("ExclusiveStartKey", {}).get("page", 0) if kwargs.get("ExclusiveStartKey") else 0
        response = {"Items": self.pages[index]}
        if index + 1 < len(self.pages):
            response["LastEvaluatedKey"] = {"page": index + 1}
        return response


def _context(remaining_ms=300_000):
    context = MagicMock()
    context.get_remaining_time_in_millis.return_value = remaining_ms
    context.function_name = "backfill-fn"
    return context


def _run(table, event=None, remaining_ms=300_000):
    lambda_client = MagicMock()
    with patch.object(backfill_template_usages, "boto3") as boto_mock:
        boto_mock.resource.return_value.Table.return_value = table
        boto_mock.client.return_value = lambda_client
        result = backfill_template_usages.handler(event or {}, _context(remaining_ms))
    return result, lambda_client


class TestBackfill:
    def test_one_record_per_distinct_pair_across_pages(self):
        table = ScanTable([
            [_step("uc-1", "s1", "t1"), _step("uc-1", "s2", "t1"), _step("uc-2", "s3", "t1")],
            [_step("uc-1", "s4", "t1"), _step("uc-1", "s5", "t2")],
        ])
        result, lambda_client = _run(table)
        written = sorted((i["pk"], i["sk"]) for i in table.put_calls)
        assert written == [("TEMPLATE#t1", "USAGE#uc-1"), ("TEMPLATE#t1", "USAGE#uc-2"), ("TEMPLATE#t2", "USAGE#uc-1")]
        for item in table.put_calls:
            assert item["template_id"] and item["usecase_id"] and item["created_at"]
        assert len(table.scan_calls) == 2
        assert result["pairs_written"] == 3 and result["pages_scanned"] == 2 and result["continued"] is False
        lambda_client.invoke.assert_not_called()

    def test_scan_filters_linked_usecase_steps_only(self):
        table = ScanTable([[]])
        _run(table)
        call = table.scan_calls[0]
        assert call["ProjectionExpression"] == "pk, sk, template_id"
        assert "begins_with(pk, :uc)" in call["FilterExpression"]
        assert "begins_with(sk, :st)" in call["FilterExpression"]
        assert "attribute_exists(template_id)" in call["FilterExpression"]
        assert call["ExpressionAttributeValues"] == {":uc": "USECASE#", ":st": "STEP#"}
        assert "ExclusiveStartKey" not in call

    def test_exclusive_start_key_from_event(self):
        table = ScanTable([[], [_step("uc-1", "s1", "t1")]])
        _run(table, {"ExclusiveStartKey": {"page": 1}})
        assert table.scan_calls[0]["ExclusiveStartKey"] == {"page": 1}
        assert len(table.scan_calls) == 1

    def test_low_remaining_time_hands_over(self):
        table = ScanTable([[_step("uc-1", "s1", "t1")], [_step("uc-2", "s2", "t1")]])
        result, lambda_client = _run(table, remaining_ms=30_000)
        # first page processed, then handed over instead of scanning page 2
        assert len(table.scan_calls) == 1
        assert [i["sk"] for i in table.put_calls] == ["USAGE#uc-1"]
        lambda_client.invoke.assert_called_once()
        kwargs = lambda_client.invoke.call_args.kwargs
        assert kwargs["FunctionName"] == "backfill-fn"
        assert kwargs["InvocationType"] == "Event"
        assert json.loads(kwargs["Payload"]) == {"ExclusiveStartKey": {"page": 1}}
        assert result["continued"] is True

    def test_low_remaining_time_without_more_pages_finishes(self):
        table = ScanTable([[_step("uc-1", "s1", "t1")]])
        result, lambda_client = _run(table, remaining_ms=30_000)
        lambda_client.invoke.assert_not_called()
        assert result["continued"] is False

    def test_put_failure_is_logged_and_run_continues(self):
        class Flaky(ScanTable):
            def put_item(self, Item, **_):  # noqa: N803
                if Item["sk"] == "USAGE#uc-1":
                    raise RuntimeError("throttled")
                return super().put_item(Item=Item)

        table = Flaky([[_step("uc-1", "s1", "t1"), _step("uc-2", "s2", "t1")]])
        result, _ = _run(table)
        assert [i["sk"] for i in table.put_calls] == ["USAGE#uc-2"]
        assert result["pairs_written"] == 1 and result["pairs_failed"] == 1

    def test_steps_without_template_id_are_ignored(self):
        table = ScanTable([[_step("uc-1", "s1"), {"pk": "USECASE#uc-1", "sk": "STEP#s2", "template_id": ""}]])
        result, _ = _run(table)
        assert table.put_calls == [] and result["pairs_written"] == 0

    def test_module_warns_against_reuse(self):
        source = open(backfill_template_usages.__file__).read()
        assert "only scan" in source.lower() or "one-off" in source.lower()
