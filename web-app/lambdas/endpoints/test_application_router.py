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
    def test_delete_user_routes_to_permissions_aware_handler(self, mock_get_handler):
        """API Gateway's resource is /users/{username}; the router matches the
        concrete path and injects userId for handlers.delete_user."""
        mock_fn = MagicMock(return_value={"statusCode": 204, "body": ""})
        mock_get_handler.return_value = mock_fn

        event = _build_event("DELETE", "/users/{username}", path_params={"username": "sub-123"})
        event["path"] = "/users/sub-123"
        response = handler(event, None)

        mock_get_handler.assert_called_once_with("handlers.delete_user")
        self.assertEqual(event["pathParameters"]["userId"], "sub-123")
        self.assertEqual(response["statusCode"], 204)

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


class TestApplicationConfigRouteDispatching(unittest.TestCase):
    """Application-level variables, secrets and datasets ride the router (no new API resources)."""

    CASES = [
        ("GET", "/applications/{id}/variables", {"id": "app-001"}, "handlers.get_application_variables"),
        ("POST", "/applications/{id}/variables", {"id": "app-001"}, "handlers.put_application_variables"),
        ("GET", "/applications/{id}/secrets", {"id": "app-001"}, "handlers.get_application_secrets"),
        ("POST", "/applications/{id}/secrets", {"id": "app-001"}, "handlers.put_application_secrets"),
        ("DELETE", "/applications/{id}/secrets", {"id": "app-001"}, "handlers.delete_application_secrets"),
        ("GET", "/applications/{id}/datasets", {"id": "app-001"}, "handlers.list_application_datasets"),
        ("POST", "/applications/{id}/datasets", {"id": "app-001"}, "handlers.create_application_dataset"),
        ("GET", "/applications/{id}/datasets/{datasetId}", {"id": "app-001", "datasetId": "ds-1"},
         "handlers.get_application_dataset"),
        ("PUT", "/applications/{id}/datasets/{datasetId}", {"id": "app-001", "datasetId": "ds-1"},
         "handlers.update_application_dataset"),
        ("DELETE", "/applications/{id}/datasets/{datasetId}", {"id": "app-001", "datasetId": "ds-1"},
         "handlers.delete_application_dataset"),
    ]

    def setUp(self):
        _handler_cache.clear()

    def test_each_config_route_dispatches_to_its_handler(self):
        for method, resource, path_params, module_path in self.CASES:
            with self.subTest(method=method, resource=resource):
                with patch("application_router._get_handler") as mock_get_handler:
                    mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
                    mock_get_handler.return_value = mock_fn

                    event = _build_event(method, resource, path_params=path_params)
                    response = handler(event, None)

                    mock_get_handler.assert_called_once_with(module_path)
                    mock_fn.assert_called_once_with(event)
                    self.assertEqual(response["statusCode"], 200)

    def test_dataset_route_extracts_path_params_from_proxy_path(self):
        """Under `/applications/{proxy+}` the resource is the proxy template; params come from the path."""
        with patch("application_router._get_handler") as mock_get_handler:
            mock_fn = MagicMock(return_value={"statusCode": 200, "body": "{}"})
            mock_get_handler.return_value = mock_fn

            event = _build_event("PUT", "/applications/{proxy+}", path_params={"proxy": "app-001/datasets/ds-1"})
            event["path"] = "/applications/app-001/datasets/ds-1"
            handler(event, None)

            mock_get_handler.assert_called_once_with("handlers.update_application_dataset")
            self.assertEqual(event["pathParameters"]["id"], "app-001")
            self.assertEqual(event["pathParameters"]["datasetId"], "ds-1")

    def test_config_routes_are_in_route_map(self):
        for method, resource, _params, module_path in self.CASES:
            self.assertEqual(ROUTE_MAP.get((method, resource)), module_path, f"Missing route: {method} {resource}")


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
