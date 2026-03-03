"""Unit tests for update_suite_execution_status handler.

Tests cover:
- Terminal status triggers test suite summary update with all five fields
- completed, partial, failed each propagate correctly
- Non-terminal status (running) does NOT trigger summary update
- Summary update failure does not fail the main request
- 404 for non-existent suite execution unchanged

**Validates: Requirements 2.1, 2.3, 3.2, 3.3**
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

from update_suite_execution_status import handler


class TestSuiteSummaryPropagation(unittest.TestCase):
    """Tests for test suite summary propagation on terminal suite status.

    **Validates: Requirements 2.1, 2.3**
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    def _build_event(self, suite_id, execution_id, body):
        return {
            "pathParameters": {"suite_id": suite_id, "execution_id": execution_id},
            "body": json.dumps(body),
            "requestContext": {
                "authorizer": {
                    "client_id": "ci-runner-client",
                    "scope": "api/executions.write",
                }
            },
        }

    def _make_suite_execution_item(self, suite_id, execution_id, successful=3, failed=1):
        return {
            "Item": {
                "pk": {"S": f"SUITE_EXECUTION#{suite_id}"},
                "sk": {"S": f"EXECUTION#{execution_id}"},
                "suite_id": {"S": suite_id},
                "status": {"S": "running"},
                "started_at": {"S": "2025-01-01T00:00:00Z"},
                "successful_usecases": {"N": str(successful)},
                "failed_usecases": {"N": str(failed)},
                "completed_usecases": {"N": str(successful + failed)},
                "total_usecases": {"N": str(successful + failed)},
                "running_usecases": {"N": "0"},
            }
        }

    def _find_summary_call(self, update_calls, suite_id):
        """Find the update_item call targeting the test suite summary record."""
        for c in update_calls:
            kwargs = c[1] if c[1] else {}
            key = kwargs.get("Key", {})
            pk_val = key.get("pk", {}).get("S", "")
            sk_val = key.get("sk", {}).get("S", "")
            if pk_val == "TEST_SUITES" and sk_val == f"SUITE#{suite_id}":
                return kwargs
        return None

    def test_completed_status_triggers_summary_update_with_all_fields(self):
        """Terminal status 'completed' updates test suite summary with all five fields.

        **Validates: Requirements 2.1, 2.3**
        """
        suite_id = "suite-prop-001"
        execution_id = "exec-prop-001"

        event = self._build_event(suite_id, execution_id, {"status": "completed"})

        with patch("update_suite_execution_status.dynamodb") as mock_ddb:
            mock_ddb.get_item.return_value = self._make_suite_execution_item(
                suite_id, execution_id, successful=5, failed=0
            )

            response = handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            summary_call = self._find_summary_call(
                mock_ddb.update_item.call_args_list, suite_id
            )
            self.assertIsNotNone(
                summary_call,
                "No update_item call found for test suite summary record"
            )

            update_expr = summary_call["UpdateExpression"]
            attr_values = summary_call["ExpressionAttributeValues"]

            # All five fields must be present
            self.assertIn("last_execution_status", update_expr)
            self.assertIn("last_execution_time", update_expr)
            self.assertIn("last_execution_id", update_expr)
            self.assertIn("last_successful_count", update_expr)
            self.assertIn("last_failed_count", update_expr)

            # Verify values
            self.assertEqual(attr_values[":status"]["S"], "completed")
            self.assertEqual(attr_values[":exec_id"]["S"], execution_id)
            self.assertEqual(attr_values[":successful"]["N"], "5")
            self.assertEqual(attr_values[":failed"]["N"], "0")

    def test_partial_status_propagates_correctly(self):
        """Terminal status 'partial' updates test suite summary.

        **Validates: Requirements 2.1**
        """
        suite_id = "suite-prop-002"
        execution_id = "exec-prop-002"

        event = self._build_event(suite_id, execution_id, {"status": "partial"})

        with patch("update_suite_execution_status.dynamodb") as mock_ddb:
            mock_ddb.get_item.return_value = self._make_suite_execution_item(
                suite_id, execution_id, successful=2, failed=3
            )

            response = handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            summary_call = self._find_summary_call(
                mock_ddb.update_item.call_args_list, suite_id
            )
            self.assertIsNotNone(summary_call, "Summary update not found for 'partial'")

            attr_values = summary_call["ExpressionAttributeValues"]
            self.assertEqual(attr_values[":status"]["S"], "partial")
            self.assertEqual(attr_values[":exec_id"]["S"], execution_id)
            self.assertEqual(attr_values[":successful"]["N"], "2")
            self.assertEqual(attr_values[":failed"]["N"], "3")

    def test_failed_status_propagates_correctly(self):
        """Terminal status 'failed' updates test suite summary.

        **Validates: Requirements 2.1**
        """
        suite_id = "suite-prop-003"
        execution_id = "exec-prop-003"

        event = self._build_event(suite_id, execution_id, {"status": "failed"})

        with patch("update_suite_execution_status.dynamodb") as mock_ddb:
            mock_ddb.get_item.return_value = self._make_suite_execution_item(
                suite_id, execution_id, successful=0, failed=4
            )

            response = handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            summary_call = self._find_summary_call(
                mock_ddb.update_item.call_args_list, suite_id
            )
            self.assertIsNotNone(summary_call, "Summary update not found for 'failed'")

            attr_values = summary_call["ExpressionAttributeValues"]
            self.assertEqual(attr_values[":status"]["S"], "failed")
            self.assertEqual(attr_values[":exec_id"]["S"], execution_id)
            self.assertEqual(attr_values[":successful"]["N"], "0")
            self.assertEqual(attr_values[":failed"]["N"], "4")


class TestNonTerminalNoSummaryUpdate(unittest.TestCase):
    """Non-terminal status (running) does NOT trigger summary update.

    **Validates: Requirements 3.2**
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    def test_running_status_does_not_trigger_summary_update(self):
        """status=running should only update suite execution record, not summary.

        **Validates: Requirements 3.2**
        """
        suite_id = "suite-nonterminal-001"
        execution_id = "exec-nonterminal-001"

        event = {
            "pathParameters": {"suite_id": suite_id, "execution_id": execution_id},
            "body": json.dumps({"status": "running"}),
            "requestContext": {
                "authorizer": {
                    "client_id": "ci-runner-client",
                    "scope": "api/executions.write",
                }
            },
        }

        with patch("update_suite_execution_status.dynamodb") as mock_ddb:
            mock_ddb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"SUITE_EXECUTION#{suite_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                    "suite_id": {"S": suite_id},
                    "status": {"S": "pending"},
                }
            }

            response = handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            # Only 1 update_item call — suite execution record only
            self.assertEqual(mock_ddb.update_item.call_count, 1)

            # Verify no call targets TEST_SUITES
            for c in mock_ddb.update_item.call_args_list:
                kwargs = c[1] if c[1] else {}
                key = kwargs.get("Key", {})
                self.assertNotEqual(
                    key.get("pk", {}).get("S", ""), "TEST_SUITES",
                    "Non-terminal status should NOT update test suite summary"
                )


class TestSummaryUpdateFailureResilience(unittest.TestCase):
    """Summary update failure does not fail the main request.

    **Validates: Requirements 2.1**
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    def test_summary_update_exception_does_not_fail_main_request(self):
        """If the summary update_item raises, the main request still returns 200.

        **Validates: Requirements 2.1**
        """
        suite_id = "suite-resilience-001"
        execution_id = "exec-resilience-001"

        event = {
            "pathParameters": {"suite_id": suite_id, "execution_id": execution_id},
            "body": json.dumps({"status": "completed"}),
            "requestContext": {
                "authorizer": {
                    "client_id": "ci-runner-client",
                    "scope": "api/executions.write",
                }
            },
        }

        with patch("update_suite_execution_status.dynamodb") as mock_ddb:
            mock_ddb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"SUITE_EXECUTION#{suite_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                    "suite_id": {"S": suite_id},
                    "status": {"S": "running"},
                    "started_at": {"S": "2025-01-01T00:00:00Z"},
                    "successful_usecases": {"N": "3"},
                    "failed_usecases": {"N": "1"},
                    "completed_usecases": {"N": "4"},
                    "total_usecases": {"N": "4"},
                    "running_usecases": {"N": "0"},
                }
            }

            # First update_item (suite execution record) succeeds,
            # second (summary) raises
            mock_ddb.update_item.side_effect = [
                None,  # suite execution record update succeeds
                Exception("DynamoDB throttle"),  # summary update fails
            ]

            response = handler(event, None)

            # Main request must still succeed
            self.assertEqual(response["statusCode"], 200)
            body = json.loads(response["body"])
            self.assertEqual(body["status"], "completed")


class TestNotFoundUnchanged(unittest.TestCase):
    """404 for non-existent suite execution unchanged.

    **Validates: Requirements 3.3**
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    def test_nonexistent_suite_execution_returns_404(self):
        """Non-existent suite execution returns 404 with error and message.

        **Validates: Requirements 3.3**
        """
        suite_id = "suite-404-001"
        execution_id = "exec-404-001"

        event = {
            "pathParameters": {"suite_id": suite_id, "execution_id": execution_id},
            "body": json.dumps({"status": "completed"}),
            "requestContext": {
                "authorizer": {
                    "client_id": "ci-runner-client",
                    "scope": "api/executions.write",
                }
            },
        }

        with patch("update_suite_execution_status.dynamodb") as mock_ddb:
            mock_ddb.get_item.return_value = {}  # No Item

            response = handler(event, None)

            self.assertEqual(response["statusCode"], 404)
            body = json.loads(response["body"])
            self.assertIn("error", body)
            self.assertIn("message", body)

            # update_item must NOT be called at all
            mock_ddb.update_item.assert_not_called()


if __name__ == "__main__":
    unittest.main()
