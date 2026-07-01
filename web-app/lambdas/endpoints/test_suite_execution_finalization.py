"""Tests for suite execution finalization logic in update_execution_status.py.

Validates:
- Last usecase completes -> suite status set to 'completed', duration_ms computed,
  last_execution propagated to suite record
- Last usecase fails -> suite status set to 'failed'
- Not all usecases done -> no finalization
- ReturnValues=ALL_NEW returns correct post-update values
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

os.environ["TABLE_NAME"] = "test-table"

from update_execution_status import handler


def _build_event(usecase_id: str, execution_id: str, body: dict):
    """Build a minimal API Gateway event for the PATCH endpoint."""
    return {
        "pathParameters": {"id": usecase_id, "executionId": execution_id},
        "body": json.dumps(body),
        "requestContext": {
            "authorizer": {
                "client_id": "ci-runner-client",
                "scope": "api/executions.write",
            }
        },
    }


def _make_suite_item(usecase_id, execution_id, suite_execution_id, suite_id):
    """Build a DynamoDB item that belongs to a suite."""
    return {
        "Item": {
            "pk": {"S": f"USECASE_EXECUTION#{usecase_id}"},
            "sk": {"S": f"EXECUTION#{execution_id}"},
            "suite_execution_id": {"S": suite_execution_id},
            "suite_id": {"S": suite_id},
        }
    }


class TestLastUsecaseCompletesSuccessfully(unittest.TestCase):
    """When the last usecase completes successfully, suite finalizes as 'completed'."""

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @patch("update_execution_status.dynamodb")
    @patch("update_execution_status.eventbridge")
    def test_last_usecase_success_finalizes_suite_as_completed(self, mock_eb, mock_ddb):
        uc_id = "uc-fin-001"
        exec_id = "exec-fin-001"
        suite_exec_id = "se-fin-001"
        suite_id = "s-fin-001"

        mock_ddb.get_item.return_value = _make_suite_item(uc_id, exec_id, suite_exec_id, suite_id)
        mock_eb.put_events.return_value = {}

        # After counter update, return ALL_NEW showing all usecases completed (3/3)
        mock_ddb.update_item.side_effect = [
            None,  # First call: execution record update
            {  # Second call: suite counter update with ReturnValues=ALL_NEW
                "Attributes": {
                    "total_usecases": {"N": "3"},
                    "completed_usecases": {"N": "3"},
                    "successful_usecases": {"N": "3"},
                    "failed_usecases": {"N": "0"},
                    "running_usecases": {"N": "0"},
                    "started_at": {"S": "2026-05-28T10:00:00Z"},
                }
            },
            None,  # Third call: finalization update (status + completed_at + duration)
            None,  # Fourth call: suite summary propagation
        ]

        event = _build_event(uc_id, exec_id, {"status": "success"})
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 200)

        # Verify finalization call (3rd update_item)
        finalize_call = mock_ddb.update_item.call_args_list[2]
        finalize_kwargs = finalize_call[1]

        update_expr = finalize_kwargs["UpdateExpression"]
        attr_values = finalize_kwargs["ExpressionAttributeValues"]

        self.assertIn("#status", finalize_kwargs["ExpressionAttributeNames"])
        self.assertEqual(attr_values[":status"], {"S": "completed"})
        self.assertIn(":completed_at", attr_values)
        self.assertIn(":duration", attr_values)

        # Verify duration is a positive number (since started_at was set)
        duration_val = int(attr_values[":duration"]["N"])
        self.assertGreaterEqual(duration_val, 0)

    @patch("update_execution_status.dynamodb")
    @patch("update_execution_status.eventbridge")
    def test_last_execution_propagated_to_suite_record(self, mock_eb, mock_ddb):
        uc_id = "uc-fin-002"
        exec_id = "exec-fin-002"
        suite_exec_id = "se-fin-002"
        suite_id = "s-fin-002"

        mock_ddb.get_item.return_value = _make_suite_item(uc_id, exec_id, suite_exec_id, suite_id)
        mock_eb.put_events.return_value = {}

        mock_ddb.update_item.side_effect = [
            None,  # Execution record update
            {  # Counter update returns ALL_NEW - all done
                "Attributes": {
                    "total_usecases": {"N": "2"},
                    "completed_usecases": {"N": "2"},
                    "successful_usecases": {"N": "2"},
                    "failed_usecases": {"N": "0"},
                    "running_usecases": {"N": "0"},
                    "started_at": {"S": "2026-05-28T09:00:00Z"},
                }
            },
            None,  # Finalization update
            None,  # Suite summary propagation
        ]

        event = _build_event(uc_id, exec_id, {"status": "success"})
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 200)

        # Verify suite summary propagation (4th update_item call)
        summary_call = mock_ddb.update_item.call_args_list[3]
        summary_kwargs = summary_call[1]

        key = summary_kwargs["Key"]
        self.assertEqual(key["pk"]["S"], "TEST_SUITES")
        self.assertEqual(key["sk"]["S"], f"SUITE#{suite_id}")

        attr_values = summary_kwargs["ExpressionAttributeValues"]
        self.assertEqual(attr_values[":status"]["S"], "completed")
        self.assertEqual(attr_values[":exec_id"]["S"], suite_exec_id)
        self.assertEqual(attr_values[":successful"]["N"], "2")
        self.assertEqual(attr_values[":failed"]["N"], "0")


class TestLastUsecaseFails(unittest.TestCase):
    """When the last usecase fails, suite finalizes as 'failed'."""

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @patch("update_execution_status.dynamodb")
    @patch("update_execution_status.eventbridge")
    def test_last_usecase_failure_finalizes_suite_as_failed(self, mock_eb, mock_ddb):
        uc_id = "uc-fin-003"
        exec_id = "exec-fin-003"
        suite_exec_id = "se-fin-003"
        suite_id = "s-fin-003"

        mock_ddb.get_item.return_value = _make_suite_item(uc_id, exec_id, suite_exec_id, suite_id)
        mock_eb.put_events.return_value = {}

        mock_ddb.update_item.side_effect = [
            None,  # Execution record update
            {  # Counter update: 3/3 completed, 1 failed
                "Attributes": {
                    "total_usecases": {"N": "3"},
                    "completed_usecases": {"N": "3"},
                    "successful_usecases": {"N": "2"},
                    "failed_usecases": {"N": "1"},
                    "running_usecases": {"N": "0"},
                    "started_at": {"S": "2026-05-28T10:00:00Z"},
                }
            },
            None,  # Finalization update
            None,  # Suite summary propagation
        ]

        event = _build_event(uc_id, exec_id, {"status": "failed"})
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 200)

        # Verify finalization sets status to 'failed'
        finalize_call = mock_ddb.update_item.call_args_list[2]
        finalize_kwargs = finalize_call[1]
        attr_values = finalize_kwargs["ExpressionAttributeValues"]
        self.assertEqual(attr_values[":status"]["S"], "failed")

        # Verify suite summary shows failure counts
        summary_call = mock_ddb.update_item.call_args_list[3]
        summary_kwargs = summary_call[1]
        summary_values = summary_kwargs["ExpressionAttributeValues"]
        self.assertEqual(summary_values[":status"]["S"], "failed")
        self.assertEqual(summary_values[":failed"]["N"], "1")
        self.assertEqual(summary_values[":successful"]["N"], "2")


class TestNotAllUsecasesDone(unittest.TestCase):
    """When not all usecases are done, no finalization occurs."""

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @patch("update_execution_status.dynamodb")
    @patch("update_execution_status.eventbridge")
    def test_partial_completion_does_not_finalize(self, mock_eb, mock_ddb):
        uc_id = "uc-fin-004"
        exec_id = "exec-fin-004"
        suite_exec_id = "se-fin-004"
        suite_id = "s-fin-004"

        mock_ddb.get_item.return_value = _make_suite_item(uc_id, exec_id, suite_exec_id, suite_id)
        mock_eb.put_events.return_value = {}

        mock_ddb.update_item.side_effect = [
            None,  # Execution record update
            {  # Counter update: only 2/5 completed
                "Attributes": {
                    "total_usecases": {"N": "5"},
                    "completed_usecases": {"N": "2"},
                    "successful_usecases": {"N": "2"},
                    "failed_usecases": {"N": "0"},
                    "running_usecases": {"N": "3"},
                    "started_at": {"S": "2026-05-28T10:00:00Z"},
                }
            },
        ]

        event = _build_event(uc_id, exec_id, {"status": "success"})
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 200)

        # Only 2 update_item calls: execution record + counter update
        # No finalization or summary propagation
        self.assertEqual(mock_ddb.update_item.call_count, 2)

    @patch("update_execution_status.dynamodb")
    @patch("update_execution_status.eventbridge")
    def test_zero_total_usecases_does_not_finalize(self, mock_eb, mock_ddb):
        uc_id = "uc-fin-005"
        exec_id = "exec-fin-005"
        suite_exec_id = "se-fin-005"
        suite_id = "s-fin-005"

        mock_ddb.get_item.return_value = _make_suite_item(uc_id, exec_id, suite_exec_id, suite_id)
        mock_eb.put_events.return_value = {}

        mock_ddb.update_item.side_effect = [
            None,  # Execution record update
            {  # Counter update: total_usecases=0 (edge case)
                "Attributes": {
                    "total_usecases": {"N": "0"},
                    "completed_usecases": {"N": "1"},
                    "successful_usecases": {"N": "1"},
                    "failed_usecases": {"N": "0"},
                    "running_usecases": {"N": "0"},
                    "started_at": {"S": "2026-05-28T10:00:00Z"},
                }
            },
        ]

        event = _build_event(uc_id, exec_id, {"status": "success"})
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        # Should not finalize when total=0
        self.assertEqual(mock_ddb.update_item.call_count, 2)


class TestReturnValuesAllNew(unittest.TestCase):
    """ReturnValues=ALL_NEW returns correct post-update values."""

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @patch("update_execution_status.dynamodb")
    @patch("update_execution_status.eventbridge")
    def test_counter_update_uses_return_values_all_new(self, mock_eb, mock_ddb):
        uc_id = "uc-fin-006"
        exec_id = "exec-fin-006"
        suite_exec_id = "se-fin-006"
        suite_id = "s-fin-006"

        mock_ddb.get_item.return_value = _make_suite_item(uc_id, exec_id, suite_exec_id, suite_id)
        mock_eb.put_events.return_value = {}

        mock_ddb.update_item.side_effect = [
            None,  # Execution record update
            {  # Counter update with ALL_NEW
                "Attributes": {
                    "total_usecases": {"N": "3"},
                    "completed_usecases": {"N": "2"},
                    "successful_usecases": {"N": "2"},
                    "failed_usecases": {"N": "0"},
                    "running_usecases": {"N": "1"},
                    "started_at": {"S": "2026-05-28T10:00:00Z"},
                }
            },
        ]

        event = _build_event(uc_id, exec_id, {"status": "success"})
        handler(event, None)

        # Verify the suite counter update includes ReturnValues='ALL_NEW'
        counter_call = mock_ddb.update_item.call_args_list[1]
        counter_kwargs = counter_call[1]
        self.assertEqual(counter_kwargs["ReturnValues"], "ALL_NEW")

    @patch("update_execution_status.dynamodb")
    @patch("update_execution_status.eventbridge")
    def test_duration_computed_from_started_at(self, mock_eb, mock_ddb):
        """Duration is computed from started_at in the suite execution record."""
        uc_id = "uc-fin-007"
        exec_id = "exec-fin-007"
        suite_exec_id = "se-fin-007"
        suite_id = "s-fin-007"

        mock_ddb.get_item.return_value = _make_suite_item(uc_id, exec_id, suite_exec_id, suite_id)
        mock_eb.put_events.return_value = {}

        mock_ddb.update_item.side_effect = [
            None,  # Execution record update
            {  # Counter update: all done
                "Attributes": {
                    "total_usecases": {"N": "1"},
                    "completed_usecases": {"N": "1"},
                    "successful_usecases": {"N": "1"},
                    "failed_usecases": {"N": "0"},
                    "running_usecases": {"N": "0"},
                    "started_at": {"S": "2026-05-28T10:00:00Z"},
                }
            },
            None,  # Finalization
            None,  # Summary
        ]

        event = _build_event(uc_id, exec_id, {"status": "success"})
        handler(event, None)

        # Verify finalization includes duration_ms
        finalize_call = mock_ddb.update_item.call_args_list[2]
        finalize_kwargs = finalize_call[1]
        self.assertIn(":duration", finalize_kwargs["ExpressionAttributeValues"])
        duration_n = finalize_kwargs["ExpressionAttributeValues"][":duration"]["N"]
        # Duration should be parseable as int and positive
        duration_ms = int(duration_n)
        self.assertGreater(duration_ms, 0)


if __name__ == "__main__":
    unittest.main()
