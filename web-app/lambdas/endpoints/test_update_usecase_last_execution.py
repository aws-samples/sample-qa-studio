"""Tests for update_usecase_last_execution Lambda.

Validates:
- Existing usecase records are updated with last execution info
- Non-existent usecase records do NOT create ghost/skeleton records (ConditionExpression guard)
- Missing required fields in event detail cause early return
- Unexpected exceptions are caught and logged without raising
"""

import os
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

# Set env before import
os.environ["TABLE_NAME"] = "test-table"

from update_usecase_last_execution import handler


def _build_event(usecase_id=None, execution_id=None, status=None, timestamp=None):
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
    return {
        "source": "nova-act-qa-studio.execution",
        "detail-type": "nova-act-qa-studio.execution.status.changed",
        "detail": detail,
    }


class TestUpdateUsecaseLastExecution(unittest.TestCase):
    """Happy-path: existing usecase gets updated."""

    @patch("update_usecase_last_execution.boto3")
    def test_updates_existing_usecase(self, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        event = _build_event(
            usecase_id="uc-001",
            execution_id="exec-001",
            status="success",
            timestamp="2026-02-24T20:00:00Z",
        )

        handler(event, None)

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]

        self.assertEqual(call_kwargs["Key"]["pk"], "USECASES")
        self.assertEqual(call_kwargs["Key"]["sk"], "USECASE#uc-001")
        self.assertIn("attribute_exists(pk)", call_kwargs["ConditionExpression"])
        self.assertEqual(call_kwargs["ExpressionAttributeValues"][":exec_id"], "exec-001")
        self.assertEqual(call_kwargs["ExpressionAttributeValues"][":status"], "success")
        self.assertEqual(
            call_kwargs["ExpressionAttributeValues"][":timestamp"],
            "2026-02-24T20:00:00Z",
        )


class TestGhostRecordPrevention(unittest.TestCase):
    """Core bug fix: non-existent usecase must NOT create a skeleton record."""

    @patch("update_usecase_last_execution.boto3")
    def test_nonexistent_usecase_does_not_create_record(self, mock_boto3):
        """When ConditionalCheckFailedException fires, no record is created."""
        mock_table = MagicMock()
        mock_dynamodb = mock_boto3.resource.return_value
        mock_dynamodb.Table.return_value = mock_table

        # Simulate ConditionalCheckFailedException
        exc_class = type("ConditionalCheckFailedException", (Exception,), {})
        mock_dynamodb.meta.client.exceptions.ConditionalCheckFailedException = exc_class
        mock_table.update_item.side_effect = exc_class("Condition not met")

        event = _build_event(
            usecase_id="nonexistent-uc",
            execution_id="exec-002",
            status="failed",
            timestamp="2026-02-24T21:00:00Z",
        )

        # Should not raise
        handler(event, None)

        # update_item was called (with the condition), but the exception was caught
        mock_table.update_item.assert_called_once()

    @patch("update_usecase_last_execution.boto3")
    def test_condition_expression_is_present(self, mock_boto3):
        """The ConditionExpression guard must always be included."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        event = _build_event(
            usecase_id="uc-003",
            execution_id="exec-003",
            status="success",
            timestamp="2026-02-24T22:00:00Z",
        )

        handler(event, None)

        call_kwargs = mock_table.update_item.call_args[1]
        self.assertEqual(call_kwargs["ConditionExpression"], "attribute_exists(pk)")


class TestMissingFields(unittest.TestCase):
    """Events with missing required fields should return early without DynamoDB calls."""

    @patch("update_usecase_last_execution.boto3")
    def test_missing_usecase_id(self, mock_boto3):
        event = _build_event(
            execution_id="exec-004", status="success", timestamp="2026-02-24T22:00:00Z"
        )
        handler(event, None)
        mock_boto3.resource.return_value.Table.return_value.update_item.assert_not_called()

    @patch("update_usecase_last_execution.boto3")
    def test_missing_execution_id(self, mock_boto3):
        event = _build_event(
            usecase_id="uc-004", status="success", timestamp="2026-02-24T22:00:00Z"
        )
        handler(event, None)
        mock_boto3.resource.return_value.Table.return_value.update_item.assert_not_called()

    @patch("update_usecase_last_execution.boto3")
    def test_missing_status(self, mock_boto3):
        event = _build_event(
            usecase_id="uc-004",
            execution_id="exec-004",
            timestamp="2026-02-24T22:00:00Z",
        )
        handler(event, None)
        mock_boto3.resource.return_value.Table.return_value.update_item.assert_not_called()

    @patch("update_usecase_last_execution.boto3")
    def test_missing_timestamp(self, mock_boto3):
        event = _build_event(
            usecase_id="uc-004", execution_id="exec-004", status="success"
        )
        handler(event, None)
        mock_boto3.resource.return_value.Table.return_value.update_item.assert_not_called()

    @patch("update_usecase_last_execution.boto3")
    def test_empty_detail(self, mock_boto3):
        event = {"source": "test", "detail-type": "test", "detail": {}}
        handler(event, None)
        mock_boto3.resource.return_value.Table.return_value.update_item.assert_not_called()


class TestUnexpectedExceptions(unittest.TestCase):
    """Unexpected errors must be caught — EventBridge handlers should not raise."""

    @patch("update_usecase_last_execution.boto3")
    def test_dynamodb_error_does_not_raise(self, mock_boto3):
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.update_item.side_effect = Exception("Connection timeout")

        event = _build_event(
            usecase_id="uc-005",
            execution_id="exec-005",
            status="failed",
            timestamp="2026-02-24T23:00:00Z",
        )

        # Should not raise
        handler(event, None)


class TestEventBridgeDetailType(unittest.TestCase):
    """Verify the DetailType fix in update_execution_status.py.

    The DetailType must use dots (status.changed) not hyphens (status-changed)
    to match the CDK EventBridge rule pattern.
    """

    def test_detail_type_uses_dots(self):
        """Read the source to confirm the DetailType string is correct."""
        import update_execution_status
        import inspect

        source = inspect.getsource(update_execution_status)
        self.assertIn(
            "nova-act-qa-studio.execution.status.changed", source
        )
        self.assertNotIn(
            "nova-act-qa-studio.execution.status-changed", source
        )


if __name__ == "__main__":
    unittest.main()
