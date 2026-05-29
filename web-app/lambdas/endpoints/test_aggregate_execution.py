"""Tests for aggregate_execution Lambda.

Validates:
- Processes success event, publishes CloudWatch metrics, updates app metadata
- Processes failed event, writes failure record with TTL
- Detects flakiness (status flip)
- Usecase with no application_id skips silently
- Missing usecase_id/execution_id returns early
- Non-terminal status returns early
- Empty environment defaults to 'default'
- Empty trigger_type defaults to 'OnDemand'
"""

import os
import time
import unittest
from unittest.mock import patch, MagicMock, ANY, call
from datetime import datetime, timezone

os.environ["TABLE_NAME"] = "test-table"

from aggregate_execution import handler, TERMINAL_STATUSES, TTL_DAYS, NAMESPACE


def _build_event(usecase_id=None, execution_id=None, status=None, timestamp=None, error_message=None):
    """Build a minimal EventBridge event."""
    detail = {}
    if usecase_id is not None:
        detail["usecase_id"] = usecase_id
    if execution_id is not None:
        detail["execution_id"] = execution_id
    if status is not None:
        detail["status"] = status
    if timestamp is not None:
        detail["timestamp"] = timestamp
    if error_message is not None:
        detail["error_message"] = error_message
    return {
        "source": "nova-act-qa-studio.execution",
        "detail-type": "nova-act-qa-studio.execution.status.changed",
        "detail": detail,
    }


class TestSuccessEventProcessing(unittest.TestCase):
    """Happy path: success event publishes metrics and updates app metadata."""

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_publishes_cloudwatch_metrics_on_success(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        # Usecase exists with application_id
        mock_table.get_item.side_effect = [
            # Usecase lookup
            {"Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "application_id": "app-001", "name": "Login"}},
            # Execution lookup
            {"Item": {"createdAt": "2026-05-28T10:00:00Z", "completedAt": "2026-05-28T10:05:00Z", "triggerType": "Scheduled"}},
            # Association lookup (environment)
            {"Item": {"environment": "prod"}},
            # Flakiness lookup
            {"Item": None},
        ]
        # Override last get_item for flakiness to return no item
        mock_table.get_item.side_effect = [
            {"Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "application_id": "app-001", "name": "Login"}},
            {"Item": {"createdAt": "2026-05-28T10:00:00Z", "completedAt": "2026-05-28T10:05:00Z", "triggerType": "Scheduled"}},
            {"Item": {"environment": "prod"}},
            {},  # No flaky record
        ]

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-001",
            status="success",
            timestamp="2026-05-28T10:05:00Z",
        )

        handler(event, None)

        # CloudWatch metrics published
        mock_cw.put_metric_data.assert_called_once()
        call_kwargs = mock_cw.put_metric_data.call_args[1]
        self.assertEqual(call_kwargs["Namespace"], NAMESPACE)
        self.assertGreater(len(call_kwargs["MetricData"]), 0)

        # App metadata updated
        update_calls = mock_table.update_item.call_args_list
        metadata_call = None
        for c in update_calls:
            kwargs = c[1] if c[1] else c[0]
            if isinstance(kwargs, dict) and kwargs.get("Key", {}).get("sk") == "METADATA":
                metadata_call = kwargs
                break
        self.assertIsNotNone(metadata_call)

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_updates_application_metadata_with_execution_info(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        mock_table.get_item.side_effect = [
            {"Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "application_id": "app-001", "name": "Login"}},
            {"Item": {"createdAt": "2026-05-28T10:00:00Z", "completedAt": "2026-05-28T10:05:00Z", "triggerType": "OnDemand"}},
            {"Item": {"environment": "default"}},
            {},  # No flaky record
        ]

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-001",
            status="success",
            timestamp="2026-05-28T10:05:00Z",
        )

        handler(event, None)

        # Find the metadata update call
        metadata_update = None
        for c in mock_table.update_item.call_args_list:
            kwargs = c[1] if c[1] else {}
            key = kwargs.get("Key", {})
            if key.get("pk") == "APPLICATION#app-001" and key.get("sk") == "METADATA":
                metadata_update = kwargs
                break

        self.assertIsNotNone(metadata_update)
        self.assertIn(":eid", metadata_update["ExpressionAttributeValues"])
        self.assertEqual(metadata_update["ExpressionAttributeValues"][":eid"], "exec-001")
        self.assertEqual(metadata_update["ExpressionAttributeValues"][":status"], "success")


class TestFailedEventProcessing(unittest.TestCase):
    """Happy path: failed event writes failure record with TTL."""

    @patch("aggregate_execution.time")
    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_writes_failure_record_with_ttl(self, mock_table_name, mock_boto3, mock_time):
        mock_time.time.return_value = 1000000
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        mock_table.get_item.side_effect = [
            {"Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "application_id": "app-001", "name": "Login test"}},
            {"Item": {"createdAt": "2026-05-28T10:00:00Z", "completedAt": "2026-05-28T10:01:00Z", "triggerType": "Scheduled"}},
            {"Item": {"environment": "staging"}},
            {},  # No flaky record
        ]

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-002",
            status="failed",
            timestamp="2026-05-28T10:01:00Z",
            error_message="Element not found",
        )

        handler(event, None)

        # Verify put_item was called for failure record
        put_calls = mock_table.put_item.call_args_list
        failure_put = None
        for c in put_calls:
            kwargs = c[1] if c[1] else {}
            item = kwargs.get("Item", {})
            if item.get("pk", "").startswith("APPLICATION_FAILURES#"):
                failure_put = item
                break

        self.assertIsNotNone(failure_put)
        self.assertEqual(failure_put["pk"], "APPLICATION_FAILURES#app-001")
        self.assertIn("FAILURE#", failure_put["sk"])
        self.assertEqual(failure_put["usecase_id"], "uc-001")
        self.assertEqual(failure_put["usecase_name"], "Login test")
        self.assertEqual(failure_put["error_message"], "Element not found")
        self.assertEqual(failure_put["environment"], "staging")
        expected_ttl = 1000000 + (TTL_DAYS * 86400)
        self.assertEqual(failure_put["ttl"], expected_ttl)


class TestFlakinessDetection(unittest.TestCase):
    """Detects flakiness when status flips from previous execution."""

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_detects_status_flip_increments_flip_count(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        mock_table.get_item.side_effect = [
            {"Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "application_id": "app-001", "name": "Login"}},
            {"Item": {"createdAt": "2026-05-28T10:00:00Z", "completedAt": "2026-05-28T10:01:00Z", "triggerType": "OnDemand"}},
            {"Item": {"environment": "prod"}},
            # Existing flaky record with last_status=success
            {"Item": {
                "pk": "APPLICATION_FLAKY#app-001",
                "sk": "USECASE#uc-001",
                "usecase_id": "uc-001",
                "usecase_name": "Login",
                "last_status": "success",
                "flip_count_7d": 2,
                "flip_count_30d": 5,
                "last_flip_at": "2026-05-27T10:00:00Z",
            }},
        ]

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-003",
            status="failed",  # Flip from success to failed
            timestamp="2026-05-28T10:01:00Z",
        )

        handler(event, None)

        # Find the flakiness update call
        flaky_update = None
        for c in mock_table.update_item.call_args_list:
            kwargs = c[1] if c[1] else {}
            key = kwargs.get("Key", {})
            if key.get("pk", "").startswith("APPLICATION_FLAKY#"):
                flaky_update = kwargs
                break

        self.assertIsNotNone(flaky_update)
        self.assertIn("flip_count_7d", flaky_update["UpdateExpression"])
        self.assertIn("flip_count_30d", flaky_update["UpdateExpression"])
        self.assertEqual(flaky_update["ExpressionAttributeValues"][":one"], 1)

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_no_flip_when_same_status(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        mock_table.get_item.side_effect = [
            {"Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "application_id": "app-001", "name": "Login"}},
            {"Item": {"createdAt": "2026-05-28T10:00:00Z", "completedAt": "2026-05-28T10:01:00Z", "triggerType": "OnDemand"}},
            {"Item": {"environment": "prod"}},
            # Existing flaky record with last_status=success
            {"Item": {
                "pk": "APPLICATION_FLAKY#app-001",
                "sk": "USECASE#uc-001",
                "usecase_id": "uc-001",
                "usecase_name": "Login",
                "last_status": "success",
                "flip_count_7d": 2,
                "flip_count_30d": 5,
                "last_flip_at": "2026-05-27T10:00:00Z",
            }},
        ]

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-004",
            status="success",  # Same as last_status - no flip
            timestamp="2026-05-28T10:01:00Z",
        )

        handler(event, None)

        # Find the flakiness update call - should only update last_status, not flip counts
        flaky_update = None
        for c in mock_table.update_item.call_args_list:
            kwargs = c[1] if c[1] else {}
            key = kwargs.get("Key", {})
            if key.get("pk", "").startswith("APPLICATION_FLAKY#"):
                flaky_update = kwargs
                break

        self.assertIsNotNone(flaky_update)
        # Should NOT contain flip_count increment
        self.assertNotIn("flip_count_7d = flip_count_7d + :one", flaky_update["UpdateExpression"])


class TestUsecaseWithNoApplicationId(unittest.TestCase):
    """Usecase with no application_id skips aggregation silently."""

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_skips_when_no_application_id(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        # Usecase exists but has no application_id
        mock_table.get_item.return_value = {
            "Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "name": "Standalone test"}
        }

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-005",
            status="success",
            timestamp="2026-05-28T10:00:00Z",
        )

        # Should not raise
        handler(event, None)

        # CloudWatch should NOT be called
        mock_cw.put_metric_data.assert_not_called()

        # No update_item calls (no metadata update)
        mock_table.update_item.assert_not_called()


class TestMissingRequiredFields(unittest.TestCase):
    """Missing usecase_id or execution_id returns early."""

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_missing_usecase_id_returns_early(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        event = _build_event(
            execution_id="exec-006",
            status="success",
            timestamp="2026-05-28T10:00:00Z",
        )

        handler(event, None)

        mock_table.get_item.assert_not_called()

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_missing_execution_id_returns_early(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        event = _build_event(
            usecase_id="uc-001",
            status="success",
            timestamp="2026-05-28T10:00:00Z",
        )

        handler(event, None)

        mock_table.get_item.assert_not_called()


class TestNonTerminalStatus(unittest.TestCase):
    """Non-terminal statuses (running, pending) are ignored."""

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_running_status_returns_early(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-007",
            status="running",
            timestamp="2026-05-28T10:00:00Z",
        )

        handler(event, None)

        mock_table.get_item.assert_not_called()

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_pending_status_returns_early(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-008",
            status="pending",
            timestamp="2026-05-28T10:00:00Z",
        )

        handler(event, None)

        mock_table.get_item.assert_not_called()


class TestEdgeCases(unittest.TestCase):
    """Edge cases: empty environment and trigger_type defaults."""

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_empty_environment_defaults_to_default(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        mock_table.get_item.side_effect = [
            {"Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "application_id": "app-001", "name": "Test"}},
            {"Item": {"createdAt": "2026-05-28T10:00:00Z", "completedAt": "2026-05-28T10:01:00Z", "triggerType": "OnDemand"}},
            # Association with empty environment
            {"Item": {"environment": ""}},
            {},  # No flaky record
        ]

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-009",
            status="success",
            timestamp="2026-05-28T10:01:00Z",
        )

        handler(event, None)

        # Verify CloudWatch was called and metrics contain 'default' environment
        mock_cw.put_metric_data.assert_called_once()
        metric_data = mock_cw.put_metric_data.call_args[1]["MetricData"]

        # Find dimension with Environment
        env_found = False
        for metric in metric_data:
            dims = metric.get("Dimensions", [])
            for dim in dims:
                if dim["Name"] == "Environment":
                    self.assertEqual(dim["Value"], "default")
                    env_found = True
        self.assertTrue(env_found, "Expected Environment dimension with 'default' value")

    @patch("aggregate_execution.boto3")
    @patch("aggregate_execution.get_table_name", return_value="test-table")
    def test_empty_trigger_type_defaults_to_ondemand(self, mock_table_name, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        mock_table.get_item.side_effect = [
            {"Item": {"pk": "USECASES", "sk": "USECASE#uc-001", "application_id": "app-001", "name": "Test"}},
            # Execution with empty triggerType
            {"Item": {"createdAt": "2026-05-28T10:00:00Z", "completedAt": "2026-05-28T10:01:00Z", "triggerType": ""}},
            {"Item": {"environment": "prod"}},
            {},  # No flaky record
        ]

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-010",
            status="success",
            timestamp="2026-05-28T10:01:00Z",
        )

        handler(event, None)

        mock_cw.put_metric_data.assert_called_once()
        metric_data = mock_cw.put_metric_data.call_args[1]["MetricData"]

        # Find dimension with TriggerType
        trigger_found = False
        for metric in metric_data:
            dims = metric.get("Dimensions", [])
            for dim in dims:
                if dim["Name"] == "TriggerType":
                    self.assertEqual(dim["Value"], "OnDemand")
                    trigger_found = True
        self.assertTrue(trigger_found, "Expected TriggerType dimension with 'OnDemand' value")


if __name__ == "__main__":
    unittest.main()
