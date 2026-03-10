"""Preservation property tests for update_execution_status Lambda endpoint.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

These tests verify that the EXISTING behavior of the PATCH endpoint is preserved.
They observe the current (unfixed) code behavior and encode it as properties:
- Status-only updates produce the correct DynamoDB update expression fields
- No `nova_session_id` attribute is ever touched when not provided
- Timestamps are set correctly based on status transitions

These tests should pass on unfixed code — they capture existing behavior.
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings

from update_execution_status import handler


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

valid_status_strategy = st.sampled_from(["pending", "running", "completed", "failed", "success"])

error_message_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=1,
        max_size=100,
    ),
)

usecase_id_strategy = st.uuids().map(str)
execution_id_strategy = st.uuids().map(str)


def _build_event(usecase_id: str, execution_id: str, body: dict) -> dict:
    """Build a minimal API Gateway event for the PATCH endpoint."""
    return {
        "pathParameters": {
            "id": usecase_id,
            "executionId": execution_id,
        },
        "body": json.dumps(body),
        "requestContext": {
            "authorizer": {
                "client_id": "ci-runner-client",
                "scope": "api/executions.write",
            }
        },
    }


class TestStatusUpdatePreservation(unittest.TestCase):
    """Property 2: Preservation — Status update DynamoDB expressions unchanged.

    **Validates: Requirements 3.3**

    For all valid status values and optional error_message combinations
    (without nova_session_id), the endpoint produces the same DynamoDB
    update expression fields as before.
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @given(
        status=valid_status_strategy,
        error_message=error_message_strategy,
        usecase_id=usecase_id_strategy,
        execution_id=execution_id_strategy,
    )
    @settings(max_examples=50, deadline=10000)
    def test_status_update_fields_match_expected(
        self, status: str, error_message, usecase_id: str, execution_id: str
    ):
        """For any valid status and optional error_message, the DynamoDB update
        expression contains exactly the expected fields and never touches
        nova_session_id.

        **Validates: Requirements 3.3**
        """
        body = {"status": status}
        if error_message is not None:
            body["error_message"] = error_message

        event = _build_event(usecase_id, execution_id, body)

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            # Execution exists
            mock_dynamodb.get_item.return_value = {
                "Item": {"pk": {"S": f"USECASE_EXECUTION#{usecase_id}"}}
            }
            mock_eb.put_events.return_value = {}

            response = handler(event, None)

            self.assertEqual(response["statusCode"], 200)

            # Inspect the DynamoDB update_item call
            mock_dynamodb.update_item.assert_called_once()
            call_kwargs = mock_dynamodb.update_item.call_args[1]
            update_expr = call_kwargs["UpdateExpression"]
            attr_values = call_kwargs["ExpressionAttributeValues"]
            attr_names = call_kwargs["ExpressionAttributeNames"]

            # --- Always present fields ---
            self.assertIn("#status", attr_names)
            self.assertEqual(attr_names["#status"], "status")
            self.assertIn(":status", attr_values)
            self.assertEqual(attr_values[":status"], {"S": status})
            self.assertIn(":updated_at", attr_values)

            # --- Conditional timestamp fields ---
            if status == "running":
                self.assertIn("started_at", update_expr)
                self.assertIn(":started_at", attr_values)
                self.assertNotIn("completed_at", update_expr)
            elif status in ("completed", "failed", "success"):
                self.assertIn("completed_at", update_expr)
                self.assertIn(":completed_at", attr_values)
                self.assertNotIn("started_at", update_expr)
            else:
                # "pending" — no extra timestamps
                self.assertNotIn("started_at", update_expr)
                self.assertNotIn("completed_at", update_expr)

            # --- Error message ---
            if error_message:
                self.assertIn("error_message", update_expr)
                self.assertIn(":error_message", attr_values)
                self.assertEqual(attr_values[":error_message"], {"S": error_message})
            else:
                self.assertNotIn("error_message", update_expr)

            # --- nova_session_id should not appear (unfixed code) ---
            self.assertNotIn("nova_session_id", update_expr)
            self.assertNotIn(":nova_session_id", str(attr_values))

    @given(status=valid_status_strategy)
    @settings(max_examples=20, deadline=10000)
    def test_response_shape_preserved(self, status: str):
        """The response body always contains execution_id, status, updated_at.

        **Validates: Requirements 3.3**
        """
        usecase_id = "uc-test-001"
        execution_id = "exec-test-001"
        event = _build_event(usecase_id, execution_id, {"status": status})

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {"Item": {"pk": {"S": "x"}}}
            mock_eb.put_events.return_value = {}

            response = handler(event, None)

            self.assertEqual(response["statusCode"], 200)
            body = json.loads(response["body"])
            self.assertIn("execution_id", body)
            self.assertIn("status", body)
            self.assertIn("updated_at", body)
            self.assertEqual(body["execution_id"], execution_id)
            self.assertEqual(body["status"], status)


class TestEventBridgePreservation(unittest.TestCase):
    """Verify EventBridge event publishing is unchanged.

    **Validates: Requirements 3.3**
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @given(
        status=valid_status_strategy,
        error_message=error_message_strategy,
    )
    @settings(max_examples=30, deadline=10000)
    def test_eventbridge_event_published_with_correct_detail(
        self, status: str, error_message
    ):
        """EventBridge event detail contains usecase_id, execution_id, status,
        timestamp, and optionally error_message — no nova_session_id.

        **Validates: Requirements 3.3**
        """
        usecase_id = "uc-eb-001"
        execution_id = "exec-eb-001"
        body = {"status": status}
        if error_message is not None:
            body["error_message"] = error_message

        event = _build_event(usecase_id, execution_id, body)

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {"Item": {"pk": {"S": "x"}}}
            mock_eb.put_events.return_value = {}

            handler(event, None)

            mock_eb.put_events.assert_called_once()
            entries = mock_eb.put_events.call_args[1]["Entries"]
            self.assertEqual(len(entries), 1)

            detail = json.loads(entries[0]["Detail"])
            self.assertEqual(detail["usecase_id"], usecase_id)
            self.assertEqual(detail["execution_id"], execution_id)
            self.assertEqual(detail["status"], status)
            self.assertIn("timestamp", detail)

            if error_message:
                self.assertEqual(detail["error_message"], error_message)
            else:
                self.assertNotIn("error_message", detail)

            # nova_session_id should not leak into EventBridge events
            self.assertNotIn("nova_session_id", detail)


if __name__ == "__main__":
    unittest.main()


class TestNovaSessionIdHandling(unittest.TestCase):
    """Unit tests for optional nova_session_id field in PATCH endpoint.

    **Validates: Requirements 2.2, 3.3**

    These tests verify that:
    - nova_session_id is persisted to DynamoDB when provided
    - Omitting nova_session_id keeps behavior identical to before
    - Empty string nova_session_id is treated as absent
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    def test_patch_with_nova_session_id_persists_to_dynamodb(self):
        """PATCH with nova_session_id includes it in the DynamoDB update expression.

        **Validates: Requirements 2.2**
        """
        event = _build_event(
            "uc-001", "exec-001",
            {"status": "running", "nova_session_id": "session-abc-123"},
        )

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {
                "Item": {"pk": {"S": "USECASE_EXECUTION#uc-001"}}
            }
            mock_eb.put_events.return_value = {}

            response = handler(event, None)

            self.assertEqual(response["statusCode"], 200)

            mock_dynamodb.update_item.assert_called_once()
            call_kwargs = mock_dynamodb.update_item.call_args[1]
            update_expr = call_kwargs["UpdateExpression"]
            attr_values = call_kwargs["ExpressionAttributeValues"]

            self.assertIn("nova_session_id", update_expr)
            self.assertIn(":nova_session_id", attr_values)
            self.assertEqual(
                attr_values[":nova_session_id"], {"S": "session-abc-123"}
            )

    def test_patch_without_nova_session_id_does_not_add_it(self):
        """PATCH without nova_session_id does not add it to the update expression.

        **Validates: Requirements 3.3**
        """
        event = _build_event(
            "uc-002", "exec-002",
            {"status": "running"},
        )

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {
                "Item": {"pk": {"S": "USECASE_EXECUTION#uc-002"}}
            }
            mock_eb.put_events.return_value = {}

            response = handler(event, None)

            self.assertEqual(response["statusCode"], 200)

            call_kwargs = mock_dynamodb.update_item.call_args[1]
            update_expr = call_kwargs["UpdateExpression"]
            attr_values = call_kwargs["ExpressionAttributeValues"]

            self.assertNotIn("nova_session_id", update_expr)
            self.assertNotIn(":nova_session_id", attr_values)

    def test_patch_with_empty_string_nova_session_id_does_not_add_it(self):
        """PATCH with empty string nova_session_id does not add it to the update expression.

        **Validates: Requirements 3.3**
        """
        event = _build_event(
            "uc-003", "exec-003",
            {"status": "failed", "nova_session_id": ""},
        )

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {
                "Item": {"pk": {"S": "USECASE_EXECUTION#uc-003"}}
            }
            mock_eb.put_events.return_value = {}

            response = handler(event, None)

            self.assertEqual(response["statusCode"], 200)

            call_kwargs = mock_dynamodb.update_item.call_args[1]
            update_expr = call_kwargs["UpdateExpression"]
            attr_values = call_kwargs["ExpressionAttributeValues"]

            self.assertNotIn("nova_session_id", update_expr)
            self.assertNotIn(":nova_session_id", attr_values)

    def test_nova_session_id_coexists_with_error_message(self):
        """PATCH with both nova_session_id and error_message persists both.

        **Validates: Requirements 2.2, 3.3**
        """
        event = _build_event(
            "uc-004", "exec-004",
            {
                "status": "failed",
                "error_message": "timeout",
                "nova_session_id": "session-xyz-789",
            },
        )

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {
                "Item": {"pk": {"S": "USECASE_EXECUTION#uc-004"}}
            }
            mock_eb.put_events.return_value = {}

            response = handler(event, None)

            self.assertEqual(response["statusCode"], 200)

            call_kwargs = mock_dynamodb.update_item.call_args[1]
            update_expr = call_kwargs["UpdateExpression"]
            attr_values = call_kwargs["ExpressionAttributeValues"]

            self.assertIn("nova_session_id", update_expr)
            self.assertEqual(
                attr_values[":nova_session_id"], {"S": "session-xyz-789"}
            )
            self.assertIn("error_message", update_expr)
            self.assertEqual(
                attr_values[":error_message"], {"S": "timeout"}
            )

    def test_nova_session_id_not_leaked_to_eventbridge(self):
        """nova_session_id should not appear in the EventBridge event detail.

        **Validates: Requirements 3.3**
        """
        event = _build_event(
            "uc-005", "exec-005",
            {"status": "running", "nova_session_id": "session-leak-check"},
        )

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {
                "Item": {"pk": {"S": "USECASE_EXECUTION#uc-005"}}
            }
            mock_eb.put_events.return_value = {}

            handler(event, None)

            mock_eb.put_events.assert_called_once()
            entries = mock_eb.put_events.call_args[1]["Entries"]
            detail = json.loads(entries[0]["Detail"])
            self.assertNotIn("nova_session_id", detail)


class TestSuiteCounterUpdates(unittest.TestCase):
    """Unit tests for suite execution counter updates on terminal usecase status.

    **Validates: Requirements 2.2, 3.1**

    When update_execution_status is called with a terminal status (success/failed)
    for an execution that belongs to a suite (has suite_execution_id and suite_id),
    the handler should atomically update suite execution counters.
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

    def _make_suite_item(self, usecase_id, execution_id, suite_execution_id, suite_id):
        return {
            "Item": {
                "pk": {"S": f"USECASE_EXECUTION#{usecase_id}"},
                "sk": {"S": f"EXECUTION#{execution_id}"},
                "suite_execution_id": {"S": suite_execution_id},
                "suite_id": {"S": suite_id},
            }
        }

    def _find_suite_counter_call(self, update_calls, suite_id):
        expected_pk = f"SUITE_EXECUTION#{suite_id}"
        for c in update_calls:
            kwargs = c[1] if c[1] else {}
            key = kwargs.get("Key", {})
            pk_val = key.get("pk", {}).get("S", "")
            if pk_val == expected_pk:
                return kwargs
        return None

    def test_success_increments_completed_and_successful_decrements_running(self):
        """status=success triggers ADD completed_usecases :inc, successful_usecases :inc, running_usecases :dec.

        **Validates: Requirements 2.2**
        """
        uc_id, exec_id = "uc-cnt-001", "exec-cnt-001"
        suite_exec_id, suite_id = "se-cnt-001", "s-cnt-001"

        event = self._build_event(uc_id, exec_id, {"status": "success"})

        with patch("update_execution_status.dynamodb") as mock_ddb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_ddb.get_item.return_value = self._make_suite_item(
                uc_id, exec_id, suite_exec_id, suite_id
            )
            mock_eb.put_events.return_value = {}

            response = handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            suite_call = self._find_suite_counter_call(
                mock_ddb.update_item.call_args_list, suite_id
            )
            self.assertIsNotNone(suite_call, "Suite counter update_item call not found")

            update_expr = suite_call["UpdateExpression"]
            self.assertIn("completed_usecases", update_expr)
            self.assertIn("successful_usecases", update_expr)
            self.assertIn("running_usecases", update_expr)
            self.assertNotIn("failed_usecases", update_expr)

            # Verify correct key targeting
            key = suite_call["Key"]
            self.assertEqual(key["pk"]["S"], f"SUITE_EXECUTION#{suite_id}")
            self.assertEqual(key["sk"]["S"], f"EXECUTION#{suite_exec_id}")

            # Verify increment/decrement values
            vals = suite_call["ExpressionAttributeValues"]
            self.assertEqual(vals[":inc"], {"N": "1"})
            self.assertEqual(vals[":dec"], {"N": "-1"})

    def test_failed_increments_completed_and_failed_decrements_running(self):
        """status=failed triggers ADD completed_usecases :inc, failed_usecases :inc, running_usecases :dec.

        **Validates: Requirements 2.2**
        """
        uc_id, exec_id = "uc-cnt-002", "exec-cnt-002"
        suite_exec_id, suite_id = "se-cnt-002", "s-cnt-002"

        event = self._build_event(uc_id, exec_id, {"status": "failed"})

        with patch("update_execution_status.dynamodb") as mock_ddb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_ddb.get_item.return_value = self._make_suite_item(
                uc_id, exec_id, suite_exec_id, suite_id
            )
            mock_eb.put_events.return_value = {}

            response = handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            suite_call = self._find_suite_counter_call(
                mock_ddb.update_item.call_args_list, suite_id
            )
            self.assertIsNotNone(suite_call, "Suite counter update_item call not found")

            update_expr = suite_call["UpdateExpression"]
            self.assertIn("completed_usecases", update_expr)
            self.assertIn("failed_usecases", update_expr)
            self.assertIn("running_usecases", update_expr)
            self.assertNotIn("successful_usecases", update_expr)

    def test_non_terminal_status_with_suite_does_not_trigger_counter_update(self):
        """Non-terminal statuses (pending, running) should not trigger suite counter updates.

        **Validates: Requirements 3.1**
        """
        for status in ["pending", "running"]:
            uc_id, exec_id = "uc-cnt-003", "exec-cnt-003"
            suite_exec_id, suite_id = "se-cnt-003", "s-cnt-003"

            event = self._build_event(uc_id, exec_id, {"status": status})

            with patch("update_execution_status.dynamodb") as mock_ddb, \
                 patch("update_execution_status.eventbridge") as mock_eb:
                mock_ddb.get_item.return_value = self._make_suite_item(
                    uc_id, exec_id, suite_exec_id, suite_id
                )
                mock_eb.put_events.return_value = {}

                response = handler(event, None)
                self.assertEqual(response["statusCode"], 200)

                # Only 1 update_item call (execution record), no suite counter update
                self.assertEqual(
                    mock_ddb.update_item.call_count, 1,
                    f"status={status}: expected 1 update_item call, got {mock_ddb.update_item.call_count}"
                )

    def test_execution_without_suite_id_does_not_trigger_counter_update(self):
        """Executions without suite_execution_id should not trigger suite counter updates.

        **Validates: Requirements 3.1**
        """
        uc_id, exec_id = "uc-cnt-004", "exec-cnt-004"

        event = self._build_event(uc_id, exec_id, {"status": "success"})

        with patch("update_execution_status.dynamodb") as mock_ddb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            # No suite_execution_id or suite_id on the item
            mock_ddb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"USECASE_EXECUTION#{uc_id}"},
                    "sk": {"S": f"EXECUTION#{exec_id}"},
                }
            }
            mock_eb.put_events.return_value = {}

            response = handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            # Only 1 update_item call (execution record)
            self.assertEqual(mock_ddb.update_item.call_count, 1)

    def test_suite_counter_update_failure_does_not_fail_main_request(self):
        """If the suite counter update_item raises an exception, the main
        request should still return 200.

        **Validates: Requirements 2.2**
        """
        uc_id, exec_id = "uc-cnt-005", "exec-cnt-005"
        suite_exec_id, suite_id = "se-cnt-005", "s-cnt-005"

        event = self._build_event(uc_id, exec_id, {"status": "success"})

        with patch("update_execution_status.dynamodb") as mock_ddb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_ddb.get_item.return_value = self._make_suite_item(
                uc_id, exec_id, suite_exec_id, suite_id
            )
            mock_eb.put_events.return_value = {}

            # First update_item call (execution record) succeeds,
            # second call (suite counter) raises
            mock_ddb.update_item.side_effect = [
                None,  # execution record update succeeds
                Exception("DynamoDB throttle"),  # suite counter update fails
            ]

            response = handler(event, None)

            # Main request should still succeed
            self.assertEqual(response["statusCode"], 200)
            body = json.loads(response["body"])
            self.assertEqual(body["status"], "success")

    def test_terminal_status_with_suite_produces_two_update_item_calls(self):
        """Terminal status with suite membership produces exactly 2 update_item calls:
        one for the execution record and one for the suite counters.

        **Validates: Requirements 2.2**
        """
        uc_id, exec_id = "uc-cnt-006", "exec-cnt-006"
        suite_exec_id, suite_id = "se-cnt-006", "s-cnt-006"

        for status in ["success", "failed"]:
            event = self._build_event(uc_id, exec_id, {"status": status})

            with patch("update_execution_status.dynamodb") as mock_ddb, \
                 patch("update_execution_status.eventbridge") as mock_eb:
                mock_ddb.get_item.return_value = self._make_suite_item(
                    uc_id, exec_id, suite_exec_id, suite_id
                )
                mock_eb.put_events.return_value = {}

                response = handler(event, None)
                self.assertEqual(response["statusCode"], 200)

                self.assertEqual(
                    mock_ddb.update_item.call_count, 2,
                    f"status={status}: expected 2 update_item calls, got {mock_ddb.update_item.call_count}"
                )
