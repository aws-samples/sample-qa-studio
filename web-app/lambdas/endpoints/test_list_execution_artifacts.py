"""
Unit tests for list_execution_artifacts Lambda function.
"""
import unittest
import json
import os
from unittest.mock import patch, MagicMock

from list_execution_artifacts import handler


class TestListExecutionArtifacts(unittest.TestCase):
    """Unit tests for the execution artifact list endpoint."""

    def setUp(self):
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['BUCKET_NAME'] = 'test-bucket'

    def _build_event(self, execution_id='exec-456', scope='api/executions.read'):
        return {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': execution_id,
            },
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': scope,
                }
            },
        }

    def _make_artifact_item(self, artifact_id, artifact_type, filename,
                            content_type, upload_status='uploaded'):
        return {
            'pk': {'S': 'EXECUTION#exec-456'},
            'sk': {'S': f'ARTIFACT#{artifact_id}'},
            'artifact_id': {'S': artifact_id},
            'execution_id': {'S': 'exec-456'},
            'type': {'S': artifact_type},
            'filename': {'S': filename},
            'content_type': {'S': content_type},
            's3_bucket': {'S': 'test-bucket'},
            's3_key': {'S': f'artifacts/exec-456/{filename}'},
            'upload_status': {'S': upload_status},
            'created_at': {'S': '2024-01-15T10:30:00Z'},
        }

    # --- test_handler_success ---
    @patch('list_execution_artifacts.get_s3_client')
    @patch('list_execution_artifacts.get_dynamodb_client')
    def test_handler_success(self, mock_get_dynamodb, mock_get_s3):
        """Returns uploaded artifacts with download URLs."""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.query.return_value = {
            'Items': [
                self._make_artifact_item('art-1', 'logs', 'runner_logs.txt', 'text/plain', 'uploaded'),
                self._make_artifact_item('art-2', 'recording', 'recording.webm', 'video/webm', 'uploaded'),
            ]
        }
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test-bucket/key?sig=abc'

        response = handler(self._build_event(), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(len(body['artifacts']), 2)

        logs_artifact = body['artifacts'][0]
        self.assertEqual(logs_artifact['artifact_id'], 'art-1')
        self.assertEqual(logs_artifact['type'], 'logs')
        self.assertEqual(logs_artifact['filename'], 'runner_logs.txt')
        self.assertTrue(logs_artifact['download_url'].startswith('https://'))

    # --- test_handler_filters_pending_artifacts ---
    @patch('list_execution_artifacts.get_s3_client')
    @patch('list_execution_artifacts.get_dynamodb_client')
    def test_handler_filters_pending_artifacts(self, mock_get_dynamodb, mock_get_s3):
        """Only returns artifacts with upload_status='uploaded'."""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.query.return_value = {
            'Items': [
                self._make_artifact_item('art-1', 'logs', 'runner_logs.txt', 'text/plain', 'uploaded'),
                self._make_artifact_item('art-2', 'recording', 'recording.webm', 'video/webm', 'pending'),
            ]
        }
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test-bucket/key?sig=abc'

        response = handler(self._build_event(), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(len(body['artifacts']), 1)
        self.assertEqual(body['artifacts'][0]['artifact_id'], 'art-1')

    # --- test_handler_empty_results ---
    @patch('list_execution_artifacts.get_s3_client')
    @patch('list_execution_artifacts.get_dynamodb_client')
    def test_handler_empty_results(self, mock_get_dynamodb, mock_get_s3):
        """No artifacts returns empty array."""
        mock_dynamodb = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_dynamodb.query.return_value = {'Items': []}

        response = handler(self._build_event(), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['artifacts'], [])

    # --- test_handler_missing_scope_returns_403 ---
    def test_handler_missing_scope_returns_403(self):
        """Missing api/executions.read scope returns 403."""
        response = handler(self._build_event(scope='api/usecases.read'), None)

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])

    # --- test_handler_missing_execution_id_returns_400 ---
    def test_handler_missing_execution_id_returns_400(self):
        """Missing executionId path parameter returns 400."""
        event = {
            'pathParameters': {'id': 'usecase-123'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/executions.read',
                }
            },
        }
        response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('is required', body['error'])

    # --- test_handler_dynamodb_error_returns_500 ---
    @patch('list_execution_artifacts.get_dynamodb_client')
    def test_handler_dynamodb_error_returns_500(self, mock_get_dynamodb):
        """DynamoDB query failure returns 500."""
        from botocore.exceptions import ClientError

        mock_dynamodb = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_dynamodb.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalError', 'Message': 'DDB failure'}},
            'Query',
        )

        response = handler(self._build_event(), None)

        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertIn('Failed to list artifacts', body['error'])

    # --- test_handler_uses_query_not_scan ---
    @patch('list_execution_artifacts.get_s3_client')
    @patch('list_execution_artifacts.get_dynamodb_client')
    def test_handler_uses_query_not_scan(self, mock_get_dynamodb, mock_get_s3):
        """Verifies DynamoDB query (not scan) is used with correct key condition."""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        mock_dynamodb.query.return_value = {'Items': []}

        handler(self._build_event(execution_id='exec-789'), None)

        mock_dynamodb.query.assert_called_once()
        call_kwargs = mock_dynamodb.query.call_args[1]
        self.assertIn('KeyConditionExpression', call_kwargs)
        self.assertEqual(
            call_kwargs['ExpressionAttributeValues'][':pk']['S'],
            'EXECUTION#exec-789'
        )
        self.assertEqual(
            call_kwargs['ExpressionAttributeValues'][':sk_prefix']['S'],
            'ARTIFACT#'
        )
        # Verify scan was NOT called
        mock_dynamodb.scan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
