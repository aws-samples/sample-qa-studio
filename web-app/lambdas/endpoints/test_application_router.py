"""Tests for application_router Lambda.

Validates:
- Routes correctly dispatch to the matching handler for each method+resource combo
- Unknown routes return 404 with descriptive error
- Handler exceptions are caught and returned as 500 with error details
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ["TABLE_NAME"] = "test-table"

from application_router import handler, ROUTE_MAP, _handler_cache


def _build_event(method: str, resource: str, path_params=None, body=None, query_params=None):
    """Build a minimal API Gateway event."""
    event = {
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
            }
        },
    }
    return event


class TestRouteDispatching(unittest.TestCase):
    """Routes are correctly dispatched to handler functions."""

    def setUp(self):
        # Clear handler cache between tests to avoid stale state
        _handler_cache.clear()

    @patch("application_router._get_handler")
    def test_get_applications_routes_to_list_handler(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "[]"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("GET", "/applications")
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.list_applications")
        mock_fn.assert_called_once_with(event)
        self.assertEqual(response["statusCode"], 200)

    @patch("application_router._get_handler")
    def test_post_applications_routes_to_create_handler(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 201, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("POST", "/applications", body={"name": "Test"})
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.create_application")
        self.assertEqual(response["statusCode"], 201)

    @patch("application_router._get_handler")
    def test_get_application_by_id_routes_correctly(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("GET", "/applications/{id}", path_params={"id": "app-001"})
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.get_application")
        self.assertEqual(response["statusCode"], 200)

    @patch("application_router._get_handler")
    def test_patch_application_routes_to_update_handler(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("PATCH", "/applications/{id}", path_params={"id": "app-001"})
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.update_application")

    @patch("application_router._get_handler")
    def test_delete_application_routes_to_delete_handler(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("DELETE", "/applications/{id}", path_params={"id": "app-001"})
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.delete_application")

    @patch("application_router._get_handler")
    def test_post_usecases_association_routes_correctly(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("POST", "/applications/{id}/usecases", path_params={"id": "app-001"})
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.associate_usecases")

    @patch("application_router._get_handler")
    def test_get_metrics_routes_correctly(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("GET", "/applications/{id}/metrics", path_params={"id": "app-001"})
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.get_application_metrics")

    @patch("application_router._get_handler")
    def test_get_failures_routes_correctly(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("GET", "/applications/{id}/failures", path_params={"id": "app-001"})
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.get_application_failures")

    @patch("application_router._get_handler")
    def test_get_flaky_routes_correctly(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("GET", "/applications/{id}/flaky", path_params={"id": "app-001"})
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.get_application_flaky")

    @patch("application_router._get_handler")
    def test_get_dashboard_overview_routes_correctly(self, mock_get_handler):
        mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
        mock_get_handler.return_value = mock_fn

        event = _build_event("GET", "/dashboard/overview")
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.get_dashboard_overview")


class TestUnknownRoutes(unittest.TestCase):
    """Unknown routes return 404."""

    def test_unknown_resource_returns_404(self):
        event = _build_event("GET", "/unknown")
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 404)
        body = json.loads(response["body"])
        self.assertIn("Route not found", body["error"])
        self.assertIn("GET", body["error"])
        self.assertIn("/unknown", body["error"])

    def test_wrong_method_on_known_resource_returns_404(self):
        event = _build_event("PUT", "/applications")
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 404)
        body = json.loads(response["body"])
        self.assertIn("Route not found", body["error"])

    def test_empty_method_and_resource_returns_404(self):
        event = {"httpMethod": "", "resource": ""}
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 404)


class TestHandlerExceptions(unittest.TestCase):
    """Handler exceptions are caught and returned as 500."""

    def setUp(self):
        _handler_cache.clear()

    @patch("application_router._get_handler")
    def test_handler_exception_returns_500_with_error_details(self, mock_get_handler):
        mock_get_handler.side_effect = ValueError("Something went wrong")

        event = _build_event("GET", "/applications")
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 500)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "Something went wrong")
        self.assertEqual(body["handler"], "handlers.list_applications")

    @patch("application_router._get_handler")
    def test_handler_runtime_error_returns_500(self, mock_get_handler):
        mock_fn = MagicMock(side_effect=RuntimeError("DynamoDB unreachable"))
        mock_get_handler.return_value = mock_fn

        event = _build_event("POST", "/applications", body={"name": "Test"})
        response = handler(event, None)

        self.assertEqual(response["statusCode"], 500)
        body = json.loads(response["body"])
        self.assertIn("DynamoDB unreachable", body["error"])


class TestRouteMapCompleteness(unittest.TestCase):
    """Verify ROUTE_MAP contains all expected routes."""

    def test_route_map_contains_all_application_routes(self):
        expected_routes = [
            ("GET", "/applications"),
            ("POST", "/applications"),
            ("GET", "/applications/{id}"),
            ("PATCH", "/applications/{id}"),
            ("DELETE", "/applications/{id}"),
            ("POST", "/applications/{id}/usecases"),
            ("DELETE", "/applications/{id}/usecases/{usecaseId}"),
            ("GET", "/applications/{id}/metrics"),
            ("GET", "/applications/{id}/failures"),
            ("GET", "/applications/{id}/flaky"),
            ("GET", "/dashboard/overview"),
        ]
        for route in expected_routes:
            self.assertIn(route, ROUTE_MAP, f"Missing route: {route}")


if __name__ == "__main__":
    unittest.main()
