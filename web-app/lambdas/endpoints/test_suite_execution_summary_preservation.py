"""Preservation property tests for suite execution summary update bugfix.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

These tests verify behavior that must NOT change after the fix is applied.
They observe the current (unfixed) code and encode baseline properties:

- Property 1: Non-suite execution preservation (no suite counter side-effects)
- Property 2: Non-terminal suite status preservation (no summary propagation)
- Property 3: Response shape preservation (expected keys and status codes)
- Property 4: EventBridge event preservation (detail shape unchanged)
- Property 5: 404 handling preservation (non-existent suite execution)

All tests MUST PASS on unfixed code — they establish the baseline.
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock

from hypothesis import given, strategies as st, settings

from update_execution_status import handler as update_execution_handler
from update_suite_execution_status import handler as update_suite_execution_handler


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

execution_status_strategy = st.sampled_from(["pending", "running", "success", "failed"])

error_message_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=1,
        max_size=80,
    ),
)

uuid_strategy = st.uuids().map(str)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_execution_event(usecase_id: str, execution_id: str, body: dict) -> dict:
    """Build a minimal API Gateway event for update_execution_status."""
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


def _build_suite_execution_event(suite_id: str, execution_id: str, body: dict) -> dict:
    """Build a minimal API Gateway event for update_suite_execution_status."""
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


class TestNonSuiteExecutionPreservation(unittest.TestCase):
    """Property 1: Non-suite execution preservation.

    **Validates: Requirements 3.1**

    For any execution status update where the execution record has NO
    suite_execution_id, DynamoDB update_item is called exactly once
    (on the execution record only). No suite counter update is attempted.
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @given(
        status=execution_status_strategy,
        error_message=error_message_strategy,
        usecase_id=uuid_strategy,
        execution_id=uuid_strategy,
    )
    @settings(max_examples=50, deadline=10000)
    def test_no_suite_counter_update_for_non_suite_execution(
        self, status: str, error_message, usecase_id: str, execution_id: str
    ):
        """For executions WITHOUT suite_execution_id, update_item is called
        exactly once (execution record only). No suite counter side-effects.

        **Validates: Requirements 3.1**
        """
        body: dict = {"status": status}
        if error_message is not None:
            body["error_message"] = error_message

        event = _build_execution_event(usecase_id, execution_id, body)

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:

            # Execution record WITHOUT suite_execution_id
            mock_dynamodb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"USECASE_EXECUTION#{usecase_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                }
            }
            mock_eb.put_events.return_value = {}

            response = update_execution_handler(event, None)

            self.assertEqual(response["statusCode"], 200)

            # update_item must be called exactly once — only the execution record
            self.assertEqual(
                mock_dynamodb.update_item.call_count, 1,
                f"Expected exactly 1 update_item call for non-suite execution, "
                f"got {mock_dynamodb.update_item.call_count}"
            )

            # Verify the single call targets the execution record, not a suite record
            call_kwargs = mock_dynamodb.update_item.call_args[1]
            key = call_kwargs["Key"]
            pk_val = key["pk"]["S"]
            self.assertTrue(
                pk_val.startswith("USECASE_EXECUTION#"),
                f"update_item PK should target execution record, got: {pk_val}"
            )


class TestNonTerminalSuiteStatusPreservation(unittest.TestCase):
    """Property 2: Non-terminal suite status preservation.

    **Validates: Requirements 3.2**

    For update_suite_execution_status with status=running (non-terminal),
    update_item is called exactly once (suite execution record only).
    No test suite summary record update.
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @given(
        suite_id=uuid_strategy,
        execution_id=uuid_strategy,
    )
    @settings(max_examples=30, deadline=10000)
    def test_non_terminal_status_updates_only_suite_execution_record(
        self, suite_id: str, execution_id: str
    ):
        """Non-terminal status 'running' calls update_item exactly once
        (suite execution record only). No test suite summary propagation.

        **Validates: Requirements 3.2**
        """
        event = _build_suite_execution_event(
            suite_id, execution_id, {"status": "running"}
        )

        with patch("update_suite_execution_status.dynamodb") as mock_dynamodb:
            mock_dynamodb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"SUITE_EXECUTION#{suite_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                    "suite_id": {"S": suite_id},
                    "status": {"S": "pending"},
                }
            }

            response = update_suite_execution_handler(event, None)

            self.assertEqual(response["statusCode"], 200)

            # update_item must be called exactly once — only the suite execution record
            self.assertEqual(
                mock_dynamodb.update_item.call_count, 1,
                f"Expected exactly 1 update_item call for non-terminal suite status, "
                f"got {mock_dynamodb.update_item.call_count}"
            )

            # Verify the single call targets the suite execution record
            call_kwargs = mock_dynamodb.update_item.call_args[1]
            key = call_kwargs["Key"]
            pk_val = key["pk"]["S"]
            self.assertTrue(
                pk_val.startswith("SUITE_EXECUTION#"),
                f"update_item PK should target suite execution record, got: {pk_val}"
            )

            # Verify no call targets TEST_SUITES (summary record)
            for c in mock_dynamodb.update_item.call_args_list:
                kwargs = c[1] if c[1] else {}
                key = kwargs.get("Key", {})
                self.assertNotEqual(
                    key.get("pk", {}).get("S", ""), "TEST_SUITES",
                    "Non-terminal status should NOT update test suite summary"
                )


class TestResponseShapePreservation(unittest.TestCase):
    """Property 3: Response shape preservation.

    **Validates: Requirements 3.1, 3.2, 3.3**

    For both endpoints with valid inputs, verify response body contains
    expected keys and status code is 200.
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @given(
        status=execution_status_strategy,
        usecase_id=uuid_strategy,
        execution_id=uuid_strategy,
    )
    @settings(max_examples=40, deadline=10000)
    def test_update_execution_status_response_shape(
        self, status: str, usecase_id: str, execution_id: str
    ):
        """update_execution_status response contains execution_id, status,
        updated_at and returns 200.

        **Validates: Requirements 3.1, 3.3**
        """
        event = _build_execution_event(
            usecase_id, execution_id, {"status": status}
        )

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {
                "Item": {"pk": {"S": f"USECASE_EXECUTION#{usecase_id}"}}
            }
            mock_eb.put_events.return_value = {}

            response = update_execution_handler(event, None)

            self.assertEqual(response["statusCode"], 200)
            body = json.loads(response["body"])
            self.assertIn("execution_id", body)
            self.assertIn("status", body)
            self.assertIn("updated_at", body)
            self.assertEqual(body["execution_id"], execution_id)
            self.assertEqual(body["status"], status)

    @given(
        status=st.sampled_from(["running", "completed", "partial", "failed"]),
        suite_id=uuid_strategy,
        execution_id=uuid_strategy,
    )
    @settings(max_examples=40, deadline=10000)
    def test_update_suite_execution_status_response_shape(
        self, status: str, suite_id: str, execution_id: str
    ):
        """update_suite_execution_status response contains suite_execution_id,
        status, updated_at and returns 200.

        **Validates: Requirements 3.2, 3.3**
        """
        event = _build_suite_execution_event(
            suite_id, execution_id, {"status": status}
        )

        with patch("update_suite_execution_status.dynamodb") as mock_dynamodb:
            mock_dynamodb.get_item.return_value = {
                "Item": {
                    "pk": {"S": f"SUITE_EXECUTION#{suite_id}"},
                    "sk": {"S": f"EXECUTION#{execution_id}"},
                    "suite_id": {"S": suite_id},
                    "status": {"S": "running"},
                    "started_at": {"S": "2025-01-01T00:00:00Z"},
                    "successful_usecases": {"N": "3"},
                    "failed_usecases": {"N": "1"},
                    "completed_usecases": {"N": "4"},
                    "total_usecases": {"N": "5"},
                    "running_usecases": {"N": "1"},
                }
            }

            response = update_suite_execution_handler(event, None)

            self.assertEqual(response["statusCode"], 200)
            body = json.loads(response["body"])
            self.assertIn("suite_execution_id", body)
            self.assertIn("status", body)
            self.assertIn("updated_at", body)
            self.assertEqual(body["suite_execution_id"], execution_id)
            self.assertEqual(body["status"], status)


class TestEventBridgeEventPreservation(unittest.TestCase):
    """Property 4: EventBridge event preservation.

    **Validates: Requirements 3.4**

    For update_execution_status, verify EventBridge put_events is called
    with the same detail shape (usecase_id, execution_id, status, timestamp)
    regardless of suite membership.
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @given(
        status=execution_status_strategy,
        usecase_id=uuid_strategy,
        execution_id=uuid_strategy,
        has_suite=st.booleans(),
    )
    @settings(max_examples=50, deadline=10000)
    def test_eventbridge_detail_shape_unchanged_regardless_of_suite(
        self, status: str, usecase_id: str, execution_id: str, has_suite: bool
    ):
        """EventBridge event detail contains usecase_id, execution_id,
        status, timestamp — regardless of whether execution belongs to a suite.

        **Validates: Requirements 3.4**
        """
        event = _build_execution_event(
            usecase_id, execution_id, {"status": status}
        )

        item: dict = {
            "pk": {"S": f"USECASE_EXECUTION#{usecase_id}"},
            "sk": {"S": f"EXECUTION#{execution_id}"},
        }
        if has_suite:
            item["suite_execution_id"] = {"S": "suite-exec-eb-001"}
            item["suite_id"] = {"S": "suite-eb-001"}

        with patch("update_execution_status.dynamodb") as mock_dynamodb, \
             patch("update_execution_status.eventbridge") as mock_eb:
            mock_dynamodb.get_item.return_value = {"Item": item}
            mock_eb.put_events.return_value = {}

            response = update_execution_handler(event, None)
            self.assertEqual(response["statusCode"], 200)

            # EventBridge put_events must be called exactly once
            mock_eb.put_events.assert_called_once()
            entries = mock_eb.put_events.call_args[1]["Entries"]
            self.assertEqual(len(entries), 1)

            entry = entries[0]
            self.assertEqual(entry["Source"], "nova-act-qa-studio.execution")
            self.assertEqual(
                entry["DetailType"],
                "nova-act-qa-studio.execution.status-changed",
            )

            detail = json.loads(entry["Detail"])
            # Required keys in event detail
            self.assertIn("usecase_id", detail)
            self.assertIn("execution_id", detail)
            self.assertIn("status", detail)
            self.assertIn("timestamp", detail)

            self.assertEqual(detail["usecase_id"], usecase_id)
            self.assertEqual(detail["execution_id"], execution_id)
            self.assertEqual(detail["status"], status)


class TestNotFoundHandlingPreservation(unittest.TestCase):
    """Property 5: 404 handling preservation.

    **Validates: Requirements 3.3**

    For update_suite_execution_status with a non-existent suite execution,
    verify 404 response is returned unchanged.
    """

    def setUp(self):
        os.environ["TABLE_NAME"] = "test-table"

    @given(
        status=st.sampled_from(["running", "completed", "partial", "failed"]),
        suite_id=uuid_strategy,
        execution_id=uuid_strategy,
    )
    @settings(max_examples=30, deadline=10000)
    def test_nonexistent_suite_execution_returns_404(
        self, status: str, suite_id: str, execution_id: str
    ):
        """Non-existent suite execution returns 404 with error and message keys.

        **Validates: Requirements 3.3**
        """
        event = _build_suite_execution_event(
            suite_id, execution_id, {"status": status}
        )

        with patch("update_suite_execution_status.dynamodb") as mock_dynamodb:
            # get_item returns no Item — suite execution does not exist
            mock_dynamodb.get_item.return_value = {}

            response = update_suite_execution_handler(event, None)

            self.assertEqual(response["statusCode"], 404)
            body = json.loads(response["body"])
            self.assertIn("error", body)
            self.assertIn("message", body)

            # update_item must NOT be called at all
            mock_dynamodb.update_item.assert_not_called()


if __name__ == "__main__":
    unittest.main()
