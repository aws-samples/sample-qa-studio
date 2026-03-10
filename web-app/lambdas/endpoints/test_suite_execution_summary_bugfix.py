"""Bug condition exploration tests for suite execution summary update.

**Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**

These tests demonstrate the three root causes of the bug:
1. update_execution_status does not update suite execution counters
2. update_suite_execution_status does not propagate to test suite summary
3. update_test_suite_summary omits last_execution_id

CRITICAL: These tests should fail on unfixed code — failure confirms the bugs exist.
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock, call

from update_execution_status import handler as update_execution_handler
from update_suite_execution_status import handler as update_suite_execution_handler
from handle_task_state_change import update_test_suite_summary


class TestCounterUpdateMissing(unittest.TestCase):
    """Root Cause 1: update_execution_status does not update suite execution counters.

    When a CI/CD runner calls update_execution_status with a terminal status
    (success/failed) for an execution that belongs to a suite, the suite
    execution counters should be atomically updated.

    On UNFIXED code: update_item is called only once (execution record),
    never on the suite execution record — test FAILS.

    **Validates: Requirements 1.2, 2.2**
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    def _build_event(self, usecase_id, execution_id, body):
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

    def test_success_status_updates_suite_counters(self):
        """Terminal status 'success' with suite_execution_id should trigger
        suite execution counter update (completed +1, successful +1, running -1).

        **Validates: Requirements 2.2**
        """
        usecase_id = "uc-suite-001"
        execution_id = "exec-suite-001"
        suite_execution_id = "suite-exec-001"
        suite_id = "suite-001"

        event = self._build_event(usecase_id, execution_id, {"status": "success"})

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:

            # get_item returns execution record WITH suite_execution_id and suite_id
            mock_dynamodb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"USECASE_EXECUTION#{usecase_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                    "suite_execution_id": {"S": suite_execution_id},
                    "suite_id": {"S": suite_id},
                }
            }
            mock_eb.put_events.return_value = {}

            response = update_execution_handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            # The handler should call update_item at least twice:
            # 1. Update execution record status
            # 2. Update suite execution counters
            update_calls = mock_dynamodb.update_item.call_args_list
            self.assertGreaterEqual(
                len(update_calls), 2,
                f"Expected at least 2 update_item calls (execution + suite counters), "
                f"got {len(update_calls)}"
            )

            # Find the suite counter update call
            suite_counter_call = None
            expected_pk = f"SUITE_EXECUTION#{suite_id}"
            expected_sk = f"EXECUTION#{suite_execution_id}"
            for c in update_calls:
                kwargs = c[1] if c[1] else {}
                key = kwargs.get("Key", {})
                pk_val = key.get("pk", {}).get("S", "")
                if pk_val == expected_pk:
                    suite_counter_call = kwargs
                    break

            self.assertIsNotNone(
                suite_counter_call,
                f"No update_item call found for suite execution record "
                f"(PK={expected_pk}, SK={expected_sk}). "
                f"Calls were: {[c[1].get('Key', {}) for c in update_calls if c[1]]}"
            )

            # Verify the counter update expression includes ADD for success counters
            update_expr = suite_counter_call.get("UpdateExpression", "")
            self.assertIn("completed_usecases", update_expr)
            self.assertIn("successful_usecases", update_expr)
            self.assertIn("running_usecases", update_expr)

    def test_failed_status_updates_suite_counters(self):
        """Terminal status 'failed' with suite_execution_id should trigger
        suite execution counter update (completed +1, failed +1, running -1).

        **Validates: Requirements 2.2**
        """
        usecase_id = "uc-suite-002"
        execution_id = "exec-suite-002"
        suite_execution_id = "suite-exec-002"
        suite_id = "suite-002"

        event = self._build_event(usecase_id, execution_id, {"status": "failed"})

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:

            mock_dynamodb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"USECASE_EXECUTION#{usecase_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                    "suite_execution_id": {"S": suite_execution_id},
                    "suite_id": {"S": suite_id},
                }
            }
            mock_eb.put_events.return_value = {}

            response = update_execution_handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            update_calls = mock_dynamodb.update_item.call_args_list
            self.assertGreaterEqual(
                len(update_calls), 2,
                f"Expected at least 2 update_item calls (execution + suite counters), "
                f"got {len(update_calls)}"
            )

            # Find the suite counter update call
            suite_counter_call = None
            expected_pk = f"SUITE_EXECUTION#{suite_id}"
            for c in update_calls:
                kwargs = c[1] if c[1] else {}
                key = kwargs.get("Key", {})
                pk_val = key.get("pk", {}).get("S", "")
                if pk_val == expected_pk:
                    suite_counter_call = kwargs
                    break

            self.assertIsNotNone(
                suite_counter_call,
                "No update_item call found for suite execution record"
            )

            update_expr = suite_counter_call.get("UpdateExpression", "")
            self.assertIn("completed_usecases", update_expr)
            self.assertIn("failed_usecases", update_expr)
            self.assertIn("running_usecases", update_expr)



class TestSummaryPropagationMissing(unittest.TestCase):
    """Root Cause 2: update_suite_execution_status does not propagate to test suite summary.

    When a CI/CD runner calls update_suite_execution_status with a terminal
    status (completed/partial/failed), the test suite summary record
    (PK=TEST_SUITES, SK=SUITE#{suite_id}) should be updated with
    last_execution_status, last_execution_time, last_execution_id,
    last_successful_count, last_failed_count.

    On UNFIXED code: update_item is called only once (suite execution record),
    never on the test suite summary — test FAILS.

    **Validates: Requirements 1.1, 2.1, 2.3**
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

    def test_completed_status_updates_test_suite_summary(self):
        """Terminal status 'completed' should update the test suite summary record
        with last_execution_status, last_execution_time, last_execution_id,
        last_successful_count, last_failed_count.

        **Validates: Requirements 2.1, 2.3**
        """
        suite_id = "suite-summary-001"
        execution_id = "suite-exec-summary-001"

        event = self._build_event(suite_id, execution_id, {"status": "completed"})

        with patch("update_suite_execution_status.dynamodb") as mock_dynamodb:
            # get_item returns suite execution record with counters and suite_id
            mock_dynamodb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"SUITE_EXECUTION#{suite_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                    "suite_id": {"S": suite_id},
                    "status": {"S": "running"},
                    "started_at": {"S": "2025-01-01T00:00:00Z"},
                    "successful_usecases": {"N": "5"},
                    "failed_usecases": {"N": "0"},
                    "completed_usecases": {"N": "5"},
                    "total_usecases": {"N": "5"},
                    "running_usecases": {"N": "0"},
                }
            }

            response = update_suite_execution_handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            # The handler should call update_item at least twice:
            # 1. Update suite execution record status
            # 2. Update test suite summary record
            update_calls = mock_dynamodb.update_item.call_args_list
            self.assertGreaterEqual(
                len(update_calls), 2,
                f"Expected at least 2 update_item calls (suite execution + test suite summary), "
                f"got {len(update_calls)}"
            )

            # Find the test suite summary update call
            summary_call = None
            for c in update_calls:
                kwargs = c[1] if c[1] else {}
                key = kwargs.get("Key", {})
                pk_val = key.get("pk", {}).get("S", "")
                if pk_val == "TEST_SUITES":
                    summary_call = kwargs
                    break

            self.assertIsNotNone(
                summary_call,
                f"No update_item call found for test suite summary record "
                f"(PK=TEST_SUITES, SK=SUITE#{suite_id}). "
                f"Calls were: {[c[1].get('Key', {}) for c in update_calls if c[1]]}"
            )

            # Verify the summary update includes all required fields
            update_expr = summary_call.get("UpdateExpression", "")
            attr_values = summary_call.get("ExpressionAttributeValues", {})

            self.assertIn("last_execution_status", update_expr)
            self.assertIn("last_execution_time", update_expr)
            self.assertIn("last_execution_id", update_expr)
            self.assertIn("last_successful_count", update_expr)
            self.assertIn("last_failed_count", update_expr)

    def test_failed_status_updates_test_suite_summary(self):
        """Terminal status 'failed' should also update the test suite summary.

        **Validates: Requirements 2.1**
        """
        suite_id = "suite-summary-002"
        execution_id = "suite-exec-summary-002"

        event = self._build_event(suite_id, execution_id, {"status": "failed"})

        with patch("update_suite_execution_status.dynamodb") as mock_dynamodb:
            mock_dynamodb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"SUITE_EXECUTION#{suite_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                    "suite_id": {"S": suite_id},
                    "status": {"S": "running"},
                    "started_at": {"S": "2025-01-01T00:00:00Z"},
                    "successful_usecases": {"N": "0"},
                    "failed_usecases": {"N": "3"},
                    "completed_usecases": {"N": "3"},
                    "total_usecases": {"N": "3"},
                    "running_usecases": {"N": "0"},
                }
            }

            response = update_suite_execution_handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            update_calls = mock_dynamodb.update_item.call_args_list
            self.assertGreaterEqual(
                len(update_calls), 2,
                f"Expected at least 2 update_item calls, got {len(update_calls)}"
            )

            # Find the test suite summary update call
            summary_call = None
            for c in update_calls:
                kwargs = c[1] if c[1] else {}
                key = kwargs.get("Key", {})
                pk_val = key.get("pk", {}).get("S", "")
                if pk_val == "TEST_SUITES":
                    summary_call = kwargs
                    break

            self.assertIsNotNone(
                summary_call,
                "No update_item call found for test suite summary record"
            )


class TestLastExecutionIdMissing(unittest.TestCase):
    """Root Cause 3: update_test_suite_summary omits last_execution_id.

    The update_test_suite_summary function in handle_task_state_change.py
    builds an UpdateExpression that sets last_execution_status,
    last_successful_count, last_failed_count, and last_execution_time —
    but omits last_execution_id.

    On UNFIXED code: UpdateExpression does not contain last_execution_id — test FAILS.

    **Validates: Requirements 1.3, 2.3**
    """

    def test_update_expression_includes_last_execution_id(self):
        """update_test_suite_summary should include last_execution_id in the
        DynamoDB UpdateExpression.

        **Validates: Requirements 2.3**
        """
        mock_client = MagicMock()
        mock_client.update_item.return_value = {}

        with patch("handle_task_state_change.get_current_timestamp", return_value="2025-01-01T12:00:00Z"):
            result = update_test_suite_summary(
                client=mock_client,
                table_name="test-table",
                suite_id="suite-last-exec-001",
                suite_execution_id="exec-last-exec-001",
                last_status="completed",
                successful=5,
                failed=0,
                total=5,
            )

        mock_client.update_item.assert_called_once()
        call_kwargs = mock_client.update_item.call_args[1]
        update_expr = call_kwargs["UpdateExpression"]
        attr_values = call_kwargs["ExpressionAttributeValues"]

        # Verify last_execution_id is included in the update expression
        self.assertIn(
            "last_execution_id", update_expr,
            f"UpdateExpression does not contain 'last_execution_id'. "
            f"Expression: {update_expr}"
        )

        # Verify the execution ID value is correct
        self.assertEqual(
            attr_values[":exec_id"]["S"], "exec-last-exec-001",
            "last_execution_id value should match the suite_execution_id parameter"
        )


if __name__ == "__main__":
    unittest.main()
