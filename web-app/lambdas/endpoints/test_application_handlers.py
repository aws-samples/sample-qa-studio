"""Tests for application handler modules in handlers/ directory.

Validates:
- create_application: creates app with all fields, validates required fields
- list_applications: returns list, handles empty state
- get_application: returns app by ID, handles not found
- update_application: updates fields, handles not found
- delete_application: deletes app + associations + index record
- associate_usecases: add/remove usecases, validates input
- get_application_metrics: returns metrics with series data, handles empty data
- get_application_failures: returns failures list, respects limit
- get_application_flaky: returns sorted flaky usecases, filters zero-flip items
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime, timezone

os.environ["TABLE_NAME"] = "test-table"


def _build_event(method="GET", resource="/applications", path_params=None, body=None, query_params=None):
    """Build a minimal API Gateway event with admin scopes."""
    return {
        "httpMethod": method,
        "resource": resource,
        "pathParameters": path_params or {},
        "queryStringParameters": query_params,
        "body": json.dumps(body) if body else None,
        "requestContext": {
            "authorizer": {
                "email": "test@test.com",
                "identity_type": "user",
                "scope": "api/admin",
                "isAdmin": "true",
            }
        },
    }


# =============================================================================
# create_application tests
# =============================================================================


class TestCreateApplication(unittest.TestCase):
    """Tests for handlers/create_application.py"""

    @patch("handlers.create_application.boto3")
    @patch("handlers.create_application.generate_uuid7", return_value="app-uuid-001")
    @patch("handlers.create_application.get_current_timestamp", return_value="2026-05-28T12:00:00Z")
    @patch("handlers.create_application.get_table_name", return_value="test-table")
    def test_creates_application_with_all_fields(self, mock_table_name, mock_ts, mock_uuid, mock_boto3):
        from handlers.create_application import handle

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        event = _build_event(
            method="POST",
            resource="/applications",
            body={
                "name": "My App",
                "base_url": "https://example.com",
                "description": "A test application",
                "team": "Platform",
                "environments": ["prod", "staging"],
                "teamId": "team-a",
            },
        )

        with patch("permissions_repo.get_team", return_value={"id": "team-a"}):
            response = handle(event)

        self.assertEqual(response["statusCode"], 201)
        body = json.loads(response["body"])
        self.assertEqual(body["id"], "app-uuid-001")
        self.assertEqual(body["name"], "My App")
        self.assertEqual(body["base_url"], "https://example.com")
        self.assertEqual(body["description"], "A test application")
        self.assertEqual(body["team"], "Platform")
        self.assertEqual(body["environments"], ["prod", "staging"])
        self.assertEqual(body["created_at"], "2026-05-28T12:00:00Z")
        self.assertEqual(body["usecase_count"], 0)

        mock_client.transact_write_items.assert_called_once()

    @patch("handlers.create_application.boto3")
    @patch("handlers.create_application.get_table_name", return_value="test-table")
    def test_missing_name_returns_400(self, mock_table_name, mock_boto3):
        from handlers.create_application import handle

        event = _build_event(
            method="POST",
            resource="/applications",
            body={"base_url": "https://example.com"},
        )

        response = handle(event)

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "name is required")

    @patch("handlers.create_application.boto3")
    @patch("handlers.create_application.get_table_name", return_value="test-table")
    def test_missing_base_url_returns_400(self, mock_table_name, mock_boto3):
        from handlers.create_application import handle

        event = _build_event(
            method="POST",
            resource="/applications",
            body={"name": "My App"},
        )

        response = handle(event)

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "base_url is required")

    @patch("handlers.create_application.boto3")
    @patch("handlers.create_application.get_table_name", return_value="test-table")
    def test_empty_name_returns_400(self, mock_table_name, mock_boto3):
        from handlers.create_application import handle

        event = _build_event(
            method="POST",
            resource="/applications",
            body={"name": "   ", "base_url": "https://example.com"},
        )

        response = handle(event)

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "name is required")

    def test_scope_validation_fails_returns_403(self):
        from handlers.create_application import handle

        event = _build_event(
            method="POST",
            resource="/applications",
            body={"name": "My App", "base_url": "https://example.com"},
        )
        # Override scopes to insufficient
        event["requestContext"]["authorizer"]["scope"] = "api/usecases.read"

        response = handle(event)

        self.assertEqual(response["statusCode"], 403)
        body = json.loads(response["body"])
        self.assertIn("Missing required scopes", body["message"])


# =============================================================================
# list_applications tests
# =============================================================================


class TestListApplications(unittest.TestCase):
    """Tests for handlers/list_applications.py"""

    @patch("handlers.list_applications.boto3")
    @patch("handlers.list_applications.get_table_name", return_value="test-table")
    def test_returns_list_of_applications(self, mock_table_name, mock_boto3):
        from handlers.list_applications import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Mock index query
        mock_table.query.return_value = {
            "Items": [
                {"pk": "APPLICATIONS", "sk": "APPLICATION#app-001", "id": "app-001"},
                {"pk": "APPLICATIONS", "sk": "APPLICATION#app-002", "id": "app-002"},
            ]
        }

        # Mock batch_get_item
        mock_boto3.resource.return_value.batch_get_item.return_value = {
            "Responses": {
                "test-table": [
                    {"pk": "APPLICATION#app-001", "sk": "METADATA", "id": "app-001", "name": "App One"},
                    {"pk": "APPLICATION#app-002", "sk": "METADATA", "id": "app-002", "name": "App Two"},
                ]
            }
        }

        event = _build_event(method="GET", resource="/applications")
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(len(body), 2)
        # Verify pk/sk are stripped
        for app in body:
            self.assertNotIn("pk", app)
            self.assertNotIn("sk", app)

    @patch("handlers.list_applications.boto3")
    @patch("handlers.list_applications.get_table_name", return_value="test-table")
    def test_returns_empty_list_when_no_applications(self, mock_table_name, mock_boto3):
        from handlers.list_applications import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}

        event = _build_event(method="GET", resource="/applications")
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body, [])


# =============================================================================
# get_application tests
# =============================================================================


class _AppResolves(unittest.TestCase):
    """app_from_path finds every app (owned by team-a) except 'nonexistent-app'."""

    def setUp(self):
        resolver = patch("resource_auth.get_app_ownership",
                         side_effect=lambda a: None if a == "nonexistent-app" else {"owner_team_id": "team-a"})
        resolver.start()
        self.addCleanup(resolver.stop)


class TestGetApplication(_AppResolves):
    """Tests for handlers/get_application.py"""

    @patch("handlers.get_application.boto3")
    @patch("handlers.get_application.get_table_name", return_value="test-table")
    def test_returns_application_by_id(self, mock_table_name, mock_boto3):
        from handlers.get_application import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "pk": "APPLICATION#app-001",
                "sk": "METADATA",
                "id": "app-001",
                "name": "My App",
                "base_url": "https://example.com",
            }
        }

        event = _build_event(
            method="GET",
            resource="/applications/{id}",
            path_params={"id": "app-001"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["id"], "app-001")
        self.assertEqual(body["name"], "My App")
        self.assertNotIn("pk", body)
        self.assertNotIn("sk", body)

    @patch("handlers.get_application.boto3")
    @patch("handlers.get_application.get_table_name", return_value="test-table")
    def test_application_not_found_returns_404(self, mock_table_name, mock_boto3):
        from handlers.get_application import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        event = _build_event(
            method="GET",
            resource="/applications/{id}",
            path_params={"id": "nonexistent-app"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 404)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "Application not found")


# =============================================================================
# update_application tests
# =============================================================================


class TestUpdateApplication(unittest.TestCase):
    """Tests for handlers/update_application.py"""

    def setUp(self):
        self._patchers = [
            patch("resource_auth.get_app_ownership", return_value={"owner_team_id": "team-a"}),
            patch("permissions_repo.get_app_owner", return_value="team-a"),
            patch("permissions_repo.list_shared_access", return_value=[]),
            patch("permissions_repo.get_usecase_owner",
                  return_value={"application_id": "app-001", "owner_team_id": "team-a", "created_by": None}),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()


    @patch("handlers.update_application.boto3")
    @patch("handlers.update_application.get_table_name", return_value="test-table")
    @patch("handlers.update_application.get_current_timestamp", return_value="2026-05-28T13:00:00Z")
    def test_updates_fields_returns_200(self, mock_ts, mock_table_name, mock_boto3):
        from handlers.update_application import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        event = _build_event(
            method="PATCH",
            resource="/applications/{id}",
            path_params={"id": "app-001"},
            body={"name": "Updated App", "description": "New description"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "application updated")
        self.assertEqual(body["id"], "app-001")

        # Verify update_item was called (at least for METADATA)
        mock_table.update_item.assert_called()

    @patch("handlers.update_application.boto3")
    @patch("handlers.update_application.get_table_name", return_value="test-table")
    @patch("handlers.update_application.get_current_timestamp", return_value="2026-05-28T13:00:00Z")
    def test_application_not_found_returns_404(self, mock_ts, mock_table_name, mock_boto3):
        from handlers.update_application import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Simulate ConditionalCheckFailedException
        exc_class = type("ConditionalCheckFailedException", (Exception,), {})
        mock_table.meta.client.exceptions.ConditionalCheckFailedException = exc_class
        mock_table.update_item.side_effect = exc_class("Condition not met")

        event = _build_event(
            method="PATCH",
            resource="/applications/{id}",
            path_params={"id": "nonexistent-app"},
            body={"name": "Updated"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 404)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "Application not found")


# =============================================================================
# delete_application tests
# =============================================================================


class TestDeleteApplication(unittest.TestCase):
    """Tests for handlers/delete_application.py"""

    def setUp(self):
        self._patchers = [
            patch("resource_auth.get_app_ownership", return_value={"owner_team_id": "team-a"}),
            patch("permissions_repo.get_app_owner", return_value="team-a"),
            patch("permissions_repo.list_shared_access", return_value=[]),
            patch("permissions_repo.get_usecase_owner",
                  return_value={"application_id": "app-001", "owner_team_id": "team-a", "created_by": None}),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()


    @patch("handlers.delete_application.boto3")
    @patch("handlers.delete_application.get_table_name", return_value="test-table")
    def test_deletes_application_associations_and_index(self, mock_table_name, mock_boto3):
        from handlers.delete_application import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Mock associations query
        mock_table.query.return_value = {
            "Items": [
                {"pk": "APPLICATION#app-001", "sk": "USECASE#uc-001"},
                {"pk": "APPLICATION#app-001", "sk": "USECASE#uc-002"},
            ]
        }

        # Mock batch_writer context manager
        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        event = _build_event(
            method="DELETE",
            resource="/applications/{id}",
            path_params={"id": "app-001"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 204)
        self.assertEqual(response["body"], "")

        # Verify association records were deleted via batch_writer
        self.assertEqual(mock_batch.delete_item.call_count, 2)

        # Verify METADATA and index records were deleted
        delete_calls = mock_table.delete_item.call_args_list
        keys_deleted = [call[1]["Key"] for call in delete_calls]
        self.assertIn({"pk": "APPLICATION#app-001", "sk": "METADATA"}, keys_deleted)
        self.assertIn({"pk": "APPLICATIONS", "sk": "APPLICATION#app-001"}, keys_deleted)


# =============================================================================
# associate_usecases tests
# =============================================================================


class TestAssociateUsecases(unittest.TestCase):
    """Tests for handlers/associate_usecases.py"""

    def setUp(self):
        self._patchers = [
            patch("resource_auth.get_app_ownership", return_value={"owner_team_id": "team-a"}),
            patch("permissions_repo.get_app_owner", return_value="team-a"),
            patch("permissions_repo.list_shared_access", return_value=[]),
            patch("permissions_repo.get_usecase_owner",
                  return_value={"application_id": "app-001", "owner_team_id": "team-a", "created_by": None}),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()


    @patch("handlers.associate_usecases.boto3")
    @patch("handlers.associate_usecases.get_table_name", return_value="test-table")
    @patch("handlers.associate_usecases.get_current_timestamp", return_value="2026-05-28T14:00:00Z")
    def test_add_usecases_default_action(self, mock_ts, mock_table_name, mock_boto3):
        from handlers.associate_usecases import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        event = _build_event(
            method="POST",
            resource="/applications/{id}/usecases",
            path_params={"id": "app-001"},
            body={"usecase_ids": ["uc-001", "uc-002"]},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "usecases associated")
        self.assertEqual(body["count"], 2)

        # Verify batch_writer put_item calls
        self.assertEqual(mock_batch.put_item.call_count, 2)

    @patch("handlers.associate_usecases.boto3")
    @patch("handlers.associate_usecases.get_table_name", return_value="test-table")
    @patch("handlers.associate_usecases.get_current_timestamp", return_value="2026-05-28T14:00:00Z")
    def test_add_usecases_explicit_add_action(self, mock_ts, mock_table_name, mock_boto3):
        from handlers.associate_usecases import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        event = _build_event(
            method="POST",
            resource="/applications/{id}/usecases",
            path_params={"id": "app-001"},
            body={"usecase_ids": ["uc-001"], "action": "add", "environment": "prod"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "usecases associated")
        self.assertEqual(body["count"], 1)

    @patch("handlers.associate_usecases.boto3")
    @patch("handlers.associate_usecases.get_table_name", return_value="test-table")
    def test_remove_usecases(self, mock_table_name, mock_boto3):
        from handlers.associate_usecases import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        event = _build_event(
            method="POST",
            resource="/applications/{id}/usecases",
            path_params={"id": "app-001"},
            body={"usecase_ids": ["uc-001", "uc-002"], "action": "remove"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "usecases removed")
        self.assertEqual(body["count"], 2)

        # Verify batch_writer delete_item calls
        self.assertEqual(mock_batch.delete_item.call_count, 2)

    @patch("handlers.associate_usecases.boto3")
    @patch("handlers.associate_usecases.get_table_name", return_value="test-table")
    def test_empty_usecase_ids_returns_400(self, mock_table_name, mock_boto3):
        from handlers.associate_usecases import handle

        event = _build_event(
            method="POST",
            resource="/applications/{id}/usecases",
            path_params={"id": "app-001"},
            body={"usecase_ids": []},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "usecase_ids must be a non-empty list")

    @patch("handlers.associate_usecases.boto3")
    @patch("handlers.associate_usecases.get_table_name", return_value="test-table")
    def test_missing_usecase_ids_returns_400(self, mock_table_name, mock_boto3):
        from handlers.associate_usecases import handle

        event = _build_event(
            method="POST",
            resource="/applications/{id}/usecases",
            path_params={"id": "app-001"},
            body={"action": "add"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "usecase_ids must be a non-empty list")


# =============================================================================
# get_application_metrics tests
# =============================================================================


class TestGetApplicationMetrics(_AppResolves):
    """Tests for handlers/get_application_metrics.py"""

    @patch("handlers.get_application_metrics.boto3")
    @patch("handlers.get_application_metrics.get_table_name", return_value="test-table")
    def test_returns_metrics_with_series_data(self, mock_table_name, mock_boto3):
        from handlers.get_application_metrics import handle

        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Mock CloudWatch response
        ts1 = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "executions", "Timestamps": [ts1, ts2], "Values": [10.0, 15.0]},
                {"Id": "successes", "Timestamps": [ts1, ts2], "Values": [8.0, 12.0]},
                {"Id": "failures", "Timestamps": [ts1, ts2], "Values": [2.0, 3.0]},
                {"Id": "duration", "Timestamps": [ts1, ts2], "Values": [5000.0, 6000.0]},
            ]
        }

        # Mock flaky query
        mock_table.query.return_value = {"Items": []}

        event = _build_event(
            method="GET",
            resource="/applications/{id}/metrics",
            path_params={"id": "app-001"},
            query_params={"window": "7d"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["application_id"], "app-001")
        self.assertEqual(body["window"], "7d")
        self.assertIn("series", body)
        self.assertIn("totals", body)
        self.assertEqual(body["totals"]["total_executions"], 25)
        self.assertEqual(body["totals"]["pass_rate"], 80.0)
        self.assertEqual(len(body["series"]["executions"]), 2)

    @patch("handlers.get_application_metrics.boto3")
    @patch("handlers.get_application_metrics.get_table_name", return_value="test-table")
    def test_returns_zeros_when_no_cloudwatch_data(self, mock_table_name, mock_boto3):
        from handlers.get_application_metrics import handle

        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Empty CloudWatch response
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "executions", "Timestamps": [], "Values": []},
                {"Id": "successes", "Timestamps": [], "Values": []},
                {"Id": "failures", "Timestamps": [], "Values": []},
                {"Id": "duration", "Timestamps": [], "Values": []},
            ]
        }

        mock_table.query.return_value = {"Items": []}

        event = _build_event(
            method="GET",
            resource="/applications/{id}/metrics",
            path_params={"id": "app-001"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["totals"]["total_executions"], 0)
        self.assertEqual(body["totals"]["pass_rate"], 0)
        self.assertEqual(body["totals"]["avg_duration_ms"], 0)
        self.assertEqual(body["series"]["executions"], [])


# =============================================================================
# get_application_failures tests
# =============================================================================


class TestGetApplicationFailures(_AppResolves):
    """Tests for handlers/get_application_failures.py"""

    @patch("handlers.get_application_failures.boto3")
    @patch("handlers.get_application_failures.get_table_name", return_value="test-table")
    def test_returns_failures_list(self, mock_table_name, mock_boto3):
        from handlers.get_application_failures import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_table.query.return_value = {
            "Items": [
                {
                    "pk": "APPLICATION_FAILURES#app-001",
                    "sk": "FAILURE#2026-05-28T12:00:00Z#exec-001",
                    "usecase_id": "uc-001",
                    "usecase_name": "Login test",
                    "error_message": "Timeout waiting for element",
                    "execution_id": "exec-001",
                    "environment": "prod",
                },
                {
                    "pk": "APPLICATION_FAILURES#app-001",
                    "sk": "FAILURE#2026-05-27T10:00:00Z#exec-002",
                    "usecase_id": "uc-002",
                    "usecase_name": "Checkout test",
                    "error_message": "Element not found",
                    "execution_id": "exec-002",
                    "environment": "staging",
                },
            ]
        }

        event = _build_event(
            method="GET",
            resource="/applications/{id}/failures",
            path_params={"id": "app-001"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(len(body), 2)
        # Verify pk is stripped
        for item in body:
            self.assertNotIn("pk", item)
        self.assertEqual(body[0]["usecase_name"], "Login test")

    @patch("handlers.get_application_failures.boto3")
    @patch("handlers.get_application_failures.get_table_name", return_value="test-table")
    def test_respects_limit_parameter(self, mock_table_name, mock_boto3):
        from handlers.get_application_failures import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}

        event = _build_event(
            method="GET",
            resource="/applications/{id}/failures",
            path_params={"id": "app-001"},
            query_params={"limit": "5"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)

        # Verify limit was passed to DynamoDB query
        query_kwargs = mock_table.query.call_args[1]
        self.assertEqual(query_kwargs["Limit"], 5)

    @patch("handlers.get_application_failures.boto3")
    @patch("handlers.get_application_failures.get_table_name", return_value="test-table")
    def test_limit_capped_at_50(self, mock_table_name, mock_boto3):
        from handlers.get_application_failures import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}

        event = _build_event(
            method="GET",
            resource="/applications/{id}/failures",
            path_params={"id": "app-001"},
            query_params={"limit": "100"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)

        query_kwargs = mock_table.query.call_args[1]
        self.assertEqual(query_kwargs["Limit"], 50)


# =============================================================================
# get_application_flaky tests
# =============================================================================


class TestGetApplicationFlaky(_AppResolves):
    """Tests for handlers/get_application_flaky.py"""

    @patch("handlers.get_application_flaky.boto3")
    @patch("handlers.get_application_flaky.get_table_name", return_value="test-table")
    def test_returns_flaky_usecases_sorted_by_flip_count(self, mock_table_name, mock_boto3):
        from handlers.get_application_flaky import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_table.query.return_value = {
            "Items": [
                {
                    "pk": "APPLICATION_FLAKY#app-001",
                    "sk": "USECASE#uc-001",
                    "usecase_id": "uc-001",
                    "usecase_name": "Login test",
                    "flip_count_7d": 3,
                    "flip_count_30d": 10,
                    "last_flip_at": "2026-05-28T10:00:00Z",
                },
                {
                    "pk": "APPLICATION_FLAKY#app-001",
                    "sk": "USECASE#uc-002",
                    "usecase_id": "uc-002",
                    "usecase_name": "Checkout test",
                    "flip_count_7d": 7,
                    "flip_count_30d": 15,
                    "last_flip_at": "2026-05-28T11:00:00Z",
                },
                {
                    "pk": "APPLICATION_FLAKY#app-001",
                    "sk": "USECASE#uc-003",
                    "usecase_id": "uc-003",
                    "usecase_name": "Stable test",
                    "flip_count_7d": 0,
                    "flip_count_30d": 2,
                    "last_flip_at": "2026-05-20T10:00:00Z",
                },
            ]
        }

        event = _build_event(
            method="GET",
            resource="/applications/{id}/flaky",
            path_params={"id": "app-001"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])

        # uc-003 with flip_count_7d=0 should be filtered out
        self.assertEqual(len(body), 2)

        # Sorted by flip_count_7d descending
        self.assertEqual(body[0]["usecase_id"], "uc-002")
        self.assertEqual(body[0]["flip_count_7d"], 7)
        self.assertEqual(body[1]["usecase_id"], "uc-001")
        self.assertEqual(body[1]["flip_count_7d"], 3)

        # pk should be stripped
        for item in body:
            self.assertNotIn("pk", item)

    @patch("handlers.get_application_flaky.boto3")
    @patch("handlers.get_application_flaky.get_table_name", return_value="test-table")
    def test_filters_out_usecases_with_zero_flip_count(self, mock_table_name, mock_boto3):
        from handlers.get_application_flaky import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_table.query.return_value = {
            "Items": [
                {
                    "pk": "APPLICATION_FLAKY#app-001",
                    "sk": "USECASE#uc-001",
                    "usecase_id": "uc-001",
                    "usecase_name": "Stable test 1",
                    "flip_count_7d": 0,
                    "flip_count_30d": 0,
                },
                {
                    "pk": "APPLICATION_FLAKY#app-001",
                    "sk": "USECASE#uc-002",
                    "usecase_id": "uc-002",
                    "usecase_name": "Stable test 2",
                    "flip_count_7d": 0,
                    "flip_count_30d": 5,
                },
            ]
        }

        event = _build_event(
            method="GET",
            resource="/applications/{id}/flaky",
            path_params={"id": "app-001"},
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body, [])


# =============================================================================
# list_applications team-scoping tests
# =============================================================================


def _build_event_with_team_context(team_roles=None, is_admin="false", scopes="api/admin"):
    """Build event with team context in the authorizer."""
    return {
        "httpMethod": "GET",
        "resource": "/applications",
        "pathParameters": {},
        "queryStringParameters": None,
        "body": None,
        "requestContext": {
            "authorizer": {
                "email": "test@test.com",
                "identityType": "user",
                "scope": scopes,
                "teamRoles": json.dumps(team_roles or []),
                "isAdmin": is_admin,
            }
        },
    }


class TestListApplicationsTeamScoping(unittest.TestCase):
    """Tests for team-based filtering in list_applications."""

    @patch("handlers.list_applications.boto3")
    @patch("handlers.list_applications.get_table_name", return_value="test-table")
    def test_admin_sees_all_applications(self, mock_table_name, mock_boto3):
        from handlers.list_applications import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_table.query.return_value = {
            "Items": [
                {"pk": "APPLICATIONS", "sk": "APPLICATION#app-001", "id": "app-001"},
                {"pk": "APPLICATIONS", "sk": "APPLICATION#app-002", "id": "app-002"},
            ]
        }

        mock_boto3.resource.return_value.batch_get_item.return_value = {
            "Responses": {
                "test-table": [
                    {"pk": "APPLICATION#app-001", "sk": "METADATA", "id": "app-001", "name": "App One", "team": "alpha"},
                    {"pk": "APPLICATION#app-002", "sk": "METADATA", "id": "app-002", "name": "App Two", "team": "beta"},
                ]
            }
        }

        event = _build_event_with_team_context(is_admin="true")
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(len(body), 2)
        # Admin apps should all have source=owned
        for app in body:
            self.assertEqual(app["source"], "owned")

    @patch("handlers.list_applications.boto3")
    @patch("handlers.list_applications.get_table_name", return_value="test-table")
    def test_team_member_sees_filtered_applications(self, mock_table_name, mock_boto3):
        from handlers.list_applications import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_table.query.return_value = {
            "Items": [
                {"pk": "APPLICATIONS", "sk": "APPLICATION#app-001", "id": "app-001"},
                {"pk": "APPLICATIONS", "sk": "APPLICATION#app-002", "id": "app-002"},
                {"pk": "APPLICATIONS", "sk": "APPLICATION#app-003", "id": "app-003"},
            ]
        }

        mock_boto3.resource.return_value.batch_get_item.return_value = {
            "Responses": {
                "test-table": [
                    {"pk": "APPLICATION#app-001", "sk": "METADATA", "id": "app-001", "name": "Alpha App", "team": "alpha"},
                    {"pk": "APPLICATION#app-002", "sk": "METADATA", "id": "app-002", "name": "Beta App", "team": "beta"},
                    {"pk": "APPLICATION#app-003", "sk": "METADATA", "id": "app-003", "name": "Gamma App", "team": "gamma"},
                ]
            }
        }

        # User belongs to team-alpha-editor only
        team_roles = [{"team_id": "alpha", "role": "editor", "group_name": "team-alpha-editor"}]
        event = _build_event_with_team_context(
            team_roles=team_roles,
            is_admin="false",
            scopes="api/applications.read api/usecases.read",
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], "app-001")
        self.assertEqual(body[0]["source"], "owned")

    @patch("handlers.list_applications.boto3")
    @patch("handlers.list_applications.get_table_name", return_value="test-table")
    def test_unassigned_user_gets_empty_list(self, mock_table_name, mock_boto3):
        from handlers.list_applications import handle

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        mock_table.query.return_value = {
            "Items": [
                {"pk": "APPLICATIONS", "sk": "APPLICATION#app-001", "id": "app-001"},
            ]
        }

        mock_boto3.resource.return_value.batch_get_item.return_value = {
            "Responses": {
                "test-table": [
                    {"pk": "APPLICATION#app-001", "sk": "METADATA", "id": "app-001", "name": "Some App", "team": "alpha"},
                ]
            }
        }

        # No team roles
        event = _build_event_with_team_context(
            team_roles=[],
            is_admin="false",
            scopes="api/applications.read",
        )
        response = handle(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body, [])


if __name__ == "__main__":
    unittest.main()


# =============================================================================
# H-3: application create/update/delete need Team Lead of the owning team
# =============================================================================


def _team_event(method, resource, team_roles, path_params=None, body=None,
                scope="api/applications.read api/applications.write", is_admin=False):
    return {
        "httpMethod": method,
        "resource": resource,
        "pathParameters": path_params or {},
        "queryStringParameters": None,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {
                "sub": "caller-sub",
                "email": "caller@example.com",
                "identityType": "user",
                "scope": "api/admin" if is_admin else scope,
                "teamRoles": json.dumps(team_roles),
                "isAdmin": "true" if is_admin else "false",
            }
        },
    }


_LEAD_A = [{"team_id": "team-a", "role": "team_lead"}]
_EDITOR_A = [{"team_id": "team-a", "role": "editor"}]
_LEAD_B = [{"team_id": "team-b", "role": "team_lead"}]
_EDITOR_B = [{"team_id": "team-b", "role": "editor"}]
_APP_BODY = {"name": "App", "base_url": "https://a.example.com", "teamId": "team-a"}


@patch("handlers.create_application.get_table_name", return_value="test-table")
@patch("handlers.create_application.boto3")
class TestCreateApplicationAuthz(unittest.TestCase):
    def _call(self, team_roles, body=_APP_BODY, team=({"id": "team-a"}), is_admin=False):
        from handlers.create_application import handle
        with patch("permissions_repo.get_team", return_value=team) as mock_get_team:
            resp = handle(_team_event("POST", "/applications", team_roles, body=body, is_admin=is_admin))
        return resp, mock_get_team

    def test_editor_gets_403(self, mock_boto3, _):
        resp, mock_team = self._call(_EDITOR_A)
        self.assertEqual(resp["statusCode"], 403)
        mock_boto3.client.return_value.transact_write_items.assert_not_called()
        mock_team.assert_not_called()

    def test_team_lead_of_other_team_gets_403(self, mock_boto3, _):
        resp, _team = self._call(_LEAD_B)
        self.assertEqual(resp["statusCode"], 403)
        mock_boto3.client.return_value.transact_write_items.assert_not_called()

    def test_team_lead_of_own_team_gets_201(self, mock_boto3, _):
        resp, _team = self._call(_LEAD_A)
        self.assertEqual(resp["statusCode"], 201)
        body = json.loads(resp["body"])
        self.assertEqual(body["owner_team_id"], "team-a")
        self.assertEqual(body["gsi2pk"], "OWNERTEAM#team-a")
        mock_boto3.client.return_value.transact_write_items.assert_called_once()

    def test_missing_team_id_gets_400(self, mock_boto3, _):
        resp, _team = self._call(_LEAD_A, body={"name": "App", "base_url": "https://a"})
        self.assertEqual(resp["statusCode"], 400)
        self.assertEqual(json.loads(resp["body"])["error"], "teamId is required")

    def test_blank_team_id_gets_400(self, mock_boto3, _):
        resp, _team = self._call(_LEAD_A, body={**_APP_BODY, "teamId": "  "})
        self.assertEqual(resp["statusCode"], 400)

    def test_unknown_team_gets_404(self, mock_boto3, _):
        resp, _team = self._call([], team=None, is_admin=True)
        self.assertEqual(resp["statusCode"], 404)
        mock_boto3.client.return_value.transact_write_items.assert_not_called()

    def test_admin_can_pick_any_team(self, mock_boto3, _):
        resp, _team = self._call([], is_admin=True)
        self.assertEqual(resp["statusCode"], 201)

    def test_invalid_field_type_gets_400(self, mock_boto3, _):
        resp, _team = self._call(_LEAD_A, body={**_APP_BODY, "environments": "prod"})
        self.assertEqual(resp["statusCode"], 400)


class _AppOwnedByTeamA(unittest.TestCase):
    """Patches the app as owned by team-a, with one grant to team-b."""

    GRANT = {"grant_id": "g-1", "target_team_id": "team-b", "app_id": "app-001", "level": "full"}

    def setUp(self):
        self.mock_table = MagicMock()
        self.mock_table.get_item.return_value = {"Item": {
            "pk": "APPLICATION#app-001", "sk": "METADATA", "owner_team_id": "team-a",
            "base_url": "https://old.example.com"}}
        self.mock_table.query.return_value = {"Items": []}
        self.mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=MagicMock())
        self.mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        patchers = [
            patch("resource_auth.get_app_ownership", return_value={"owner_team_id": "team-a"}),
            patch("resource_auth.list_shared_access", return_value=[self.GRANT]),
            patch("permissions_repo.get_app_owner", return_value="team-a"),
            patch("permissions_repo.list_shared_access", return_value=[
                self.GRANT, {**self.GRANT, "grant_id": "g-2", "app_id": "other-app"}]),
            patch("permissions_repo.revoke_shared_access"),
            patch("handlers.update_application.boto3"),
            patch("handlers.delete_application.boto3"),
            patch("handlers.update_application.log_permission_change"),
        ]
        self.mocks = [p.start() for p in patchers]
        self.mock_revoke = self.mocks[4]
        self.mock_audit = self.mocks[7]
        for boto in (self.mocks[5], self.mocks[6]):
            boto.resource.return_value.Table.return_value = self.mock_table
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def _update(self, team_roles, body=None):
        from handlers.update_application import handle
        return handle(_team_event("PATCH", "/applications/{id}", team_roles,
                                  path_params={"id": "app-001"},
                                  body=body or {"base_url": "https://evil.example.com"}))

    def _delete(self, team_roles):
        from handlers.delete_application import handle
        return handle(_team_event("DELETE", "/applications/{id}", team_roles, path_params={"id": "app-001"}))


class TestUpdateApplicationAuthz(_AppOwnedByTeamA):
    def test_editor_in_other_team_gets_403(self):
        self.assertEqual(self._update([{"team_id": "team-c", "role": "editor"}])["statusCode"], 403)
        self.mock_table.update_item.assert_not_called()

    def test_editor_in_owner_team_gets_403(self):
        self.assertEqual(self._update(_EDITOR_A)["statusCode"], 403)
        self.mock_table.update_item.assert_not_called()

    def test_shared_team_with_full_access_cannot_change_base_url(self):
        self.assertEqual(self._update(_LEAD_B)["statusCode"], 403)
        self.mock_table.update_item.assert_not_called()
        self.mock_audit.assert_not_called()

    def test_owner_team_lead_gets_200_and_base_url_audited(self):
        resp = self._update(_LEAD_A)
        self.assertEqual(resp["statusCode"], 200)
        self.mock_table.update_item.assert_called()
        self.mock_audit.assert_called_once()
        kwargs = self.mock_audit.call_args.kwargs
        self.assertEqual(kwargs["action"], "app_base_url_change")
        self.assertEqual(kwargs["details"], {"old": "https://old.example.com", "new": "https://evil.example.com"})
        self.assertEqual(kwargs["target"], {"app_id": "app-001", "owner_team_id": "team-a"})

    def test_unchanged_base_url_not_audited(self):
        resp = self._update(_LEAD_A, body={"name": "New", "base_url": "https://old.example.com"})
        self.assertEqual(resp["statusCode"], 200)
        self.mock_audit.assert_not_called()

    def test_orphan_app_admin_only(self):
        self.mock_table.get_item.return_value = {"Item": {"owner_team_id": None, "base_url": "x"}}
        with patch("resource_auth.get_app_ownership", return_value={"owner_team_id": None}):
            self.assertEqual(self._update(_LEAD_A)["statusCode"], 403)
            from handlers.update_application import handle
            resp = handle(_team_event("PATCH", "/applications/{id}", [], path_params={"id": "app-001"},
                                      body={"name": "n"}, is_admin=True))
        self.assertEqual(resp["statusCode"], 200)


class TestDeleteApplicationAuthz(_AppOwnedByTeamA):
    def test_editor_in_other_team_gets_403(self):
        self.assertEqual(self._delete([{"team_id": "team-c", "role": "editor"}])["statusCode"], 403)
        self.mock_table.delete_item.assert_not_called()

    def test_shared_full_team_lead_gets_403(self):
        self.assertEqual(self._delete(_LEAD_B)["statusCode"], 403)
        self.mock_table.delete_item.assert_not_called()
        self.mock_revoke.assert_not_called()

    def test_owner_editor_gets_403(self):
        self.assertEqual(self._delete(_EDITOR_A)["statusCode"], 403)

    def test_owner_team_lead_gets_204_and_grants_revoked(self):
        resp = self._delete(_LEAD_A)
        self.assertEqual(resp["statusCode"], 204)
        self.assertEqual(resp["body"], "")
        self.mock_revoke.assert_called_once_with("team-a", "team-b", "app-001")
        self.mock_table.delete_item.assert_any_call(Key={"pk": "APPLICATION#app-001", "sk": "METADATA"})


@patch("handlers.associate_usecases.get_current_timestamp", return_value="2026-05-28T14:00:00Z")
@patch("handlers.associate_usecases.boto3")
class TestAssociateUsecasesAuthz(unittest.TestCase):
    def setUp(self):
        patchers = [
            patch("resource_auth.get_app_ownership", return_value={"owner_team_id": "team-a"}),
            patch("resource_auth.list_shared_access", return_value=[]),
            patch("resource_auth.get_app_owner", return_value="team-b"),
            patch("permissions_repo.get_app_owner", return_value="team-a"),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def _call(self, owners, action="add"):
        from handlers.associate_usecases import handle
        with patch("permissions_repo.get_usecase_owner", side_effect=lambda uc: owners.get(uc)):
            return handle(_team_event("POST", "/applications/{id}/usecases", _EDITOR_A,
                                      path_params={"id": "app-001"},
                                      body={"usecase_ids": list(owners) or ["uc-x"], "action": action}))

    def test_other_teams_usecase_cannot_be_pulled_in(self, mock_boto3, _):
        resp = self._call({"uc-1": {"application_id": "app-b", "owner_team_id": "team-b"}})
        self.assertEqual(resp["statusCode"], 403)
        mock_boto3.resource.return_value.Table.return_value.batch_writer.assert_not_called()

    def test_other_teams_usecase_cannot_be_detached(self, mock_boto3, _):
        resp = self._call({"uc-1": {"application_id": "app-b", "owner_team_id": "team-b"}}, action="remove")
        self.assertEqual(resp["statusCode"], 403)

    def test_orphan_usecase_admin_only(self, mock_boto3, _):
        resp = self._call({"uc-1": {"application_id": None, "owner_team_id": None}})
        self.assertEqual(resp["statusCode"], 403)

    def test_missing_usecase_404(self, mock_boto3, _):
        self.assertEqual(self._call({})["statusCode"], 404)

    def test_own_teams_usecases_allowed(self, mock_boto3, _):
        table = mock_boto3.resource.return_value.Table.return_value
        table.batch_writer.return_value.__enter__ = MagicMock(return_value=MagicMock())
        table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        resp = self._call({
            "uc-1": {"application_id": "app-001", "owner_team_id": "team-a"},
            "uc-2": {"application_id": "app-a2", "owner_team_id": "team-a"},
        })
        self.assertEqual(resp["statusCode"], 200)


class TestListTeamApplicationsAuthz(unittest.TestCase):
    def _call(self, team_roles, is_admin=False):
        from handlers.list_team_applications import handle
        apps = [{"pk": "APPLICATION#a1", "sk": "METADATA", "gsi2pk": "OWNERTEAM#team-a",
                 "gsi2sk": "APP#a1", "id": "a1", "base_url": "https://a"}]
        with patch("permissions_repo.list_team_apps", return_value=apps) as mock_list:
            resp = handle(_team_event("GET", "/teams/{id}/applications", team_roles,
                                      path_params={"id": "team-a"}, is_admin=is_admin))
        return resp, mock_list

    def test_non_member_gets_403(self):
        resp, mock_list = self._call(_EDITOR_B)
        self.assertEqual(resp["statusCode"], 403)
        mock_list.assert_not_called()

    def test_member_gets_team_apps_via_gsi(self):
        resp, mock_list = self._call([{"team_id": "team-a", "role": "viewer"}])
        self.assertEqual(resp["statusCode"], 200)
        mock_list.assert_called_once_with("team-a")
        self.assertEqual(json.loads(resp["body"]), [{"id": "a1", "base_url": "https://a"}])

    def test_admin_allowed(self):
        self.assertEqual(self._call([], is_admin=True)[0]["statusCode"], 200)
