"""Unit tests for handle_task_state_change.py — last_execution_id fix.

Tests verify that:
1. update_test_suite_summary includes last_execution_id in UpdateExpression
2. check_suite_completion passes suite_execution_id to update_test_suite_summary

**Validates: Requirements 2.3**
"""

import unittest
from unittest.mock import patch, MagicMock

from handle_task_state_change import update_test_suite_summary, check_suite_completion


class TestUpdateTestSuiteSummaryLastExecutionId(unittest.TestCase):
    """Tests that update_test_suite_summary includes last_execution_id."""

    def test_update_expression_includes_last_execution_id(self):
        """UpdateExpression should contain last_execution_id field.

        **Validates: Requirements 2.3**
        """
        mock_client = MagicMock()
        mock_client.update_item.return_value = {}

        with patch("handle_task_state_change.get_current_timestamp", return_value="2025-01-01T12:00:00Z"):
            result = update_test_suite_summary(
                client=mock_client,
                table_name="test-table",
                suite_id="suite-001",
                suite_execution_id="exec-001",
                last_status="completed",
                successful=3,
                failed=0,
                total=3,
            )

        self.assertTrue(result)
        mock_client.update_item.assert_called_once()
        call_kwargs = mock_client.update_item.call_args[1]
        update_expr = call_kwargs["UpdateExpression"]
        self.assertIn("last_execution_id", update_expr)

    def test_last_execution_id_value_matches_suite_execution_id(self):
        """ExpressionAttributeValues should map :exec_id to the suite_execution_id.

        **Validates: Requirements 2.3**
        """
        mock_client = MagicMock()
        mock_client.update_item.return_value = {}

        with patch("handle_task_state_change.get_current_timestamp", return_value="2025-06-01T00:00:00Z"):
            update_test_suite_summary(
                client=mock_client,
                table_name="test-table",
                suite_id="suite-abc",
                suite_execution_id="exec-xyz-789",
                last_status="partial",
                successful=2,
                failed=1,
                total=3,
            )

        call_kwargs = mock_client.update_item.call_args[1]
        attr_values = call_kwargs["ExpressionAttributeValues"]
        self.assertEqual(attr_values[":exec_id"]["S"], "exec-xyz-789")

    def test_existing_fields_still_present(self):
        """All previously existing fields should still be in the UpdateExpression.

        **Validates: Requirements 2.3 (preservation of existing behavior)**
        """
        mock_client = MagicMock()
        mock_client.update_item.return_value = {}

        with patch("utils.get_current_timestamp", return_value="2025-01-01T00:00:00Z"):
            update_test_suite_summary(
                client=mock_client,
                table_name="test-table",
                suite_id="suite-002",
                suite_execution_id="exec-002",
                last_status="failed",
                successful=0,
                failed=5,
                total=5,
            )

        call_kwargs = mock_client.update_item.call_args[1]
        update_expr = call_kwargs["UpdateExpression"]
        attr_values = call_kwargs["ExpressionAttributeValues"]

        # All original fields must still be present
        self.assertIn("last_execution_status", update_expr)
        self.assertIn("last_successful_count", update_expr)
        self.assertIn("last_failed_count", update_expr)
        self.assertIn("last_execution_time", update_expr)
        self.assertIn("last_execution_id", update_expr)

        # Verify values
        self.assertEqual(attr_values[":status"]["S"], "failed")
        self.assertEqual(attr_values[":successful"]["N"], "0")
        self.assertEqual(attr_values[":failed"]["N"], "5")
        self.assertEqual(attr_values[":time"]["S"], "2025-01-01T00:00:00Z")
        self.assertEqual(attr_values[":exec_id"]["S"], "exec-002")

    def test_correct_dynamo_key(self):
        """update_item should target PK=TEST_SUITES, SK=SUITE#{suite_id}.

        **Validates: Requirements 2.3**
        """
        mock_client = MagicMock()
        mock_client.update_item.return_value = {}

        with patch("handle_task_state_change.get_current_timestamp", return_value="2025-01-01T00:00:00Z"):
            update_test_suite_summary(
                client=mock_client,
                table_name="my-table",
                suite_id="suite-key-test",
                suite_execution_id="exec-key-test",
                last_status="completed",
                successful=1,
                failed=0,
                total=1,
            )

        call_kwargs = mock_client.update_item.call_args[1]
        key = call_kwargs["Key"]
        self.assertEqual(key["pk"]["S"], "TEST_SUITES")
        self.assertEqual(key["sk"]["S"], "SUITE#suite-key-test")


class TestCheckSuiteCompletionPassesSuiteExecutionId(unittest.TestCase):
    """Tests that check_suite_completion passes suite_execution_id to update_test_suite_summary."""

    def _build_suite_execution_item(self, suite_id, suite_execution_id, total, completed, successful, failed):
        """Helper to build a mock suite execution DynamoDB item."""
        return {
            'Item': {
                'pk': {'S': f'SUITE_EXECUTION#{suite_id}'},
                'sk': {'S': f'EXECUTION#{suite_execution_id}'},
                'total_usecases': {'N': str(total)},
                'completed_usecases': {'N': str(completed)},
                'successful_usecases': {'N': str(successful)},
                'failed_usecases': {'N': str(failed)},
                'started_at': {'S': '2025-01-01T00:00:00Z'},
            }
        }

    @patch("handle_task_state_change.update_test_suite_summary")
    @patch("handle_task_state_change.get_current_timestamp", return_value="2025-01-01T01:00:00Z")
    def test_passes_suite_execution_id_to_update_summary(self, mock_timestamp, mock_update_summary):
        """check_suite_completion should pass suite_execution_id as the 4th arg.

        **Validates: Requirements 2.3**
        """
        mock_client = MagicMock()
        suite_id = "suite-pass-001"
        suite_execution_id = "exec-pass-001"

        mock_client.get_item.return_value = self._build_suite_execution_item(
            suite_id, suite_execution_id, total=3, completed=3, successful=3, failed=0
        )
        mock_client.update_item.return_value = {}

        result = check_suite_completion(mock_client, "test-table", suite_id, suite_execution_id)

        self.assertTrue(result)
        mock_update_summary.assert_called_once()

        args = mock_update_summary.call_args[0]
        self.assertEqual(args[0], mock_client)        # client
        self.assertEqual(args[1], "test-table")        # table_name
        self.assertEqual(args[2], suite_id)             # suite_id
        self.assertEqual(args[3], suite_execution_id)   # suite_execution_id
        self.assertEqual(args[4], "completed")          # final_status

    @patch("handle_task_state_change.update_test_suite_summary")
    @patch("handle_task_state_change.get_current_timestamp", return_value="2025-01-01T01:00:00Z")
    def test_passes_suite_execution_id_on_partial_status(self, mock_timestamp, mock_update_summary):
        """suite_execution_id should be passed even when final status is partial.

        **Validates: Requirements 2.3**
        """
        mock_client = MagicMock()
        suite_id = "suite-partial-001"
        suite_execution_id = "exec-partial-001"

        mock_client.get_item.return_value = self._build_suite_execution_item(
            suite_id, suite_execution_id, total=4, completed=4, successful=2, failed=2
        )
        mock_client.update_item.return_value = {}

        result = check_suite_completion(mock_client, "test-table", suite_id, suite_execution_id)

        self.assertTrue(result)
        mock_update_summary.assert_called_once()
        args = mock_update_summary.call_args[0]
        self.assertEqual(args[3], suite_execution_id)
        self.assertEqual(args[4], "partial")

    @patch("handle_task_state_change.update_test_suite_summary")
    @patch("handle_task_state_change.get_current_timestamp", return_value="2025-01-01T01:00:00Z")
    def test_passes_suite_execution_id_on_failed_status(self, mock_timestamp, mock_update_summary):
        """suite_execution_id should be passed even when final status is failed.

        **Validates: Requirements 2.3**
        """
        mock_client = MagicMock()
        suite_id = "suite-fail-001"
        suite_execution_id = "exec-fail-001"

        mock_client.get_item.return_value = self._build_suite_execution_item(
            suite_id, suite_execution_id, total=2, completed=2, successful=0, failed=2
        )
        mock_client.update_item.return_value = {}

        result = check_suite_completion(mock_client, "test-table", suite_id, suite_execution_id)

        self.assertTrue(result)
        mock_update_summary.assert_called_once()
        args = mock_update_summary.call_args[0]
        self.assertEqual(args[3], suite_execution_id)
        self.assertEqual(args[4], "failed")


if __name__ == "__main__":
    unittest.main()
