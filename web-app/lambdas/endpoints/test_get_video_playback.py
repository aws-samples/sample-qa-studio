"""Unit tests for get_video_playback Lambda function"""
import unittest
import json
import os
from io import BytesIO
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from get_video_playback import handler, classify_playback_type


class TestGetVideoPlayback(unittest.TestCase):
    """Test video playback endpoint"""

    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['BUCKET_NAME'] = 'test-bucket'

    def _make_event(self, usecase_id='usecase-123', execution_id='execution-456',
                    scope='api/executions.read', path_params=None):
        """Helper to build a standard API Gateway event."""
        if path_params is not None:
            params = path_params
        else:
            params = {'id': usecase_id, 'executionId': execution_id}
        return {
            'pathParameters': params,
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': scope,
                }
            }
        }

    def _execution_record(self, trigger_type, usecase_id='usecase-123',
                          execution_id='execution-456'):
        """Helper to build a DynamoDB execution record response."""
        return {
            'Item': {
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'},
                'trigger_type': {'S': trigger_type},
            }
        }

    def _setup_rrweb_s3_mocks(self, mock_s3, usecase_id='usecase-123',
                               execution_id='execution-456',
                               session_id='session-abc'):
        """Configure S3 mock for rrweb playback path."""
        folder_prefix = f'{usecase_id}/{execution_id}/recording/{session_id}/'
        metadata = {'startTime': 1234567890, 'duration': 5000}

        def list_objects_side_effect(**kwargs):
            prefix = kwargs.get('Prefix', '')
            if prefix.endswith('recording/'):
                return {'CommonPrefixes': [{'Prefix': folder_prefix}]}
            elif 'batch_' in prefix:
                return {
                    'Contents': [
                        {'Key': f'{folder_prefix}batch_1761741997665.ndjson.gz'},
                        {'Key': f'{folder_prefix}batch_1761742001234.ndjson.gz'},
                    ]
                }
            return {}

        mock_s3.list_objects_v2.side_effect = list_objects_side_effect

        body_stream = MagicMock()
        body_stream.read.return_value = json.dumps(metadata).encode('utf-8')
        mock_s3.get_object.return_value = {'Body': body_stream}

        return metadata

    # ------------------------------------------------------------------ #
    # Happy path: rrweb playback (trigger_type=OnDemand)
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_rrweb_playback_on_demand(self, mock_get_dynamodb, mock_get_s3):
        """Verify rrweb playback response for OnDemand trigger_type"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = self._execution_record('OnDemand')
        metadata = self._setup_rrweb_s3_mocks(mock_s3)

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['playback_type'], 'rrweb')
        self.assertEqual(body['execution_id'], 'execution-456')
        self.assertEqual(body['trigger_type'], 'OnDemand')
        self.assertIsInstance(body['batches'], list)
        self.assertEqual(len(body['batches']), 2)
        self.assertIn('1761741997665', body['batches'])
        self.assertIn('1761742001234', body['batches'])
        self.assertEqual(body['metadata'], metadata)

    # ------------------------------------------------------------------ #
    # Happy path: rrweb playback (trigger_type=Scheduled)
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_rrweb_playback_scheduled(self, mock_get_dynamodb, mock_get_s3):
        """Verify rrweb playback response for Scheduled trigger_type"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = self._execution_record('Scheduled')
        metadata = self._setup_rrweb_s3_mocks(mock_s3)

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['playback_type'], 'rrweb')
        self.assertEqual(body['trigger_type'], 'Scheduled')
        self.assertIsInstance(body['batches'], list)
        self.assertEqual(body['metadata'], metadata)

    # ------------------------------------------------------------------ #
    # Happy path: rrweb playback (trigger_type=OnDemandHeadless)
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_rrweb_playback_on_demand_headless(self, mock_get_dynamodb, mock_get_s3):
        """Verify rrweb playback response for OnDemandHeadless trigger_type"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = self._execution_record('OnDemandHeadless')
        metadata = self._setup_rrweb_s3_mocks(mock_s3)

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['playback_type'], 'rrweb')
        self.assertEqual(body['trigger_type'], 'OnDemandHeadless')
        self.assertIsInstance(body['batches'], list)
        self.assertEqual(body['metadata'], metadata)

    # ------------------------------------------------------------------ #
    # Happy path: video playback (trigger_type=ci_runner)
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_video_playback_ci_runner(self, mock_get_dynamodb, mock_get_s3):
        """Verify video playback response for ci_runner trigger_type"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = self._execution_record('ci_runner')
        mock_dynamodb.query.return_value = {
            'Items': [{
                'pk': {'S': 'EXECUTION#execution-456'},
                'sk': {'S': 'ARTIFACT#artifact-789'},
                'type': {'S': 'recording'},
                'upload_status': {'S': 'uploaded'},
                's3_key': {'S': 'usecase-123/execution-456/recording.webm'},
                's3_bucket': {'S': 'test-bucket'},
                'content_type': {'S': 'video/webm'},
            }]
        }
        mock_s3.generate_presigned_url.return_value = (
            'https://s3.amazonaws.com/test-bucket/recording.webm?signature=xyz'
        )

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['playback_type'], 'video')
        self.assertEqual(body['execution_id'], 'execution-456')
        self.assertEqual(body['trigger_type'], 'ci_runner')
        self.assertIn('download_url', body)
        self.assertTrue(body['download_url'].startswith('https://'))
        self.assertEqual(body['content_type'], 'video/webm')
        self.assertEqual(body['expires_in'], 3600)

    # ------------------------------------------------------------------ #
    # 404: execution not found
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_execution_not_found_returns_404(self, mock_get_dynamodb, mock_get_s3):
        """Verify 404 when execution record does not exist"""
        mock_dynamodb = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_dynamodb.get_item.return_value = {}  # No Item

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertIn('Execution not found', body['error'])

    # ------------------------------------------------------------------ #
    # 404: rrweb path but no recording folder in S3
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_rrweb_no_recording_folder_returns_404(self, mock_get_dynamodb, mock_get_s3):
        """Verify 404 when S3 has no recording folder for rrweb path"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = self._execution_record('OnDemand')
        mock_s3.list_objects_v2.return_value = {'CommonPrefixes': []}

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertIn('Recording not found', body['error'])

    # ------------------------------------------------------------------ #
    # 404: video path but no artifact with upload_status=uploaded
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_video_no_uploaded_artifact_returns_404(self, mock_get_dynamodb, mock_get_s3):
        """Verify 404 when no recording artifact with upload_status=uploaded exists"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = self._execution_record('ci_runner')
        # Artifact exists but with wrong status
        mock_dynamodb.query.return_value = {
            'Items': [{
                'pk': {'S': 'EXECUTION#execution-456'},
                'sk': {'S': 'ARTIFACT#artifact-789'},
                'type': {'S': 'recording'},
                'upload_status': {'S': 'pending'},
                's3_key': {'S': 'usecase-123/execution-456/recording.webm'},
                's3_bucket': {'S': 'test-bucket'},
                'content_type': {'S': 'video/webm'},
            }]
        }

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertIn('Recording not found', body['error'])

    # ------------------------------------------------------------------ #
    # 400: missing path parameters
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_missing_path_parameters_returns_400(self, mock_get_dynamodb, mock_get_s3):
        """Verify 400 when pathParameters are missing"""
        event = self._make_event()
        event['pathParameters'] = None

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Missing required path parameters', body['error'])

    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_empty_path_parameters_returns_400(self, mock_get_dynamodb, mock_get_s3):
        """Verify 400 when pathParameters is empty dict"""
        event = self._make_event(path_params={})

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Missing required path parameters', body['error'])

    # ------------------------------------------------------------------ #
    # 400: unrecognized trigger_type
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_unrecognized_trigger_type_returns_400(self, mock_get_dynamodb, mock_get_s3):
        """Verify 400 when trigger_type is not recognized"""
        mock_dynamodb = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb

        mock_dynamodb.get_item.return_value = self._execution_record('unknown_type')

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Unsupported trigger type', body['error'])
        self.assertIn('unknown_type', body['message'])

    # ------------------------------------------------------------------ #
    # 500: DynamoDB ClientError
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_dynamodb_client_error_returns_500(self, mock_get_dynamodb, mock_get_s3):
        """Verify 500 when DynamoDB raises ClientError"""
        mock_dynamodb = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb

        mock_dynamodb.get_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'DynamoDB error'}},
            'GetItem'
        )

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertEqual(body['error'], 'Internal server error')
        # Must not leak internal details
        self.assertNotIn('DynamoDB', json.dumps(body))

    # ------------------------------------------------------------------ #
    # 500: S3 ClientError
    # ------------------------------------------------------------------ #
    @patch('get_video_playback.get_s3_client')
    @patch('get_video_playback.get_dynamodb_client')
    def test_s3_client_error_returns_500(self, mock_get_dynamodb, mock_get_s3):
        """Verify 500 when S3 raises ClientError during rrweb path"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = self._execution_record('OnDemand')
        mock_s3.list_objects_v2.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
            'ListObjectsV2'
        )

        response = handler(self._make_event(), None)

        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertEqual(body['error'], 'Internal server error')
        # Must not leak internal details
        self.assertNotIn('Access Denied', json.dumps(body))
        self.assertNotIn('test-bucket', json.dumps(body))

    # ------------------------------------------------------------------ #
    # 403: missing api/executions.read scope
    # ------------------------------------------------------------------ #
    def test_missing_scope_returns_403(self):
        """Verify 403 when api/executions.read scope is missing"""
        event = self._make_event(scope='api/usecases.read')

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])


class TestClassifyPlaybackType(unittest.TestCase):
    """Test classify_playback_type helper directly"""

    def test_on_demand_returns_rrweb(self):
        self.assertEqual(classify_playback_type('OnDemand'), 'rrweb')

    def test_scheduled_returns_rrweb(self):
        self.assertEqual(classify_playback_type('Scheduled'), 'rrweb')

    def test_on_demand_headless_returns_rrweb(self):
        self.assertEqual(classify_playback_type('OnDemandHeadless'), 'rrweb')

    def test_ci_runner_returns_video(self):
        self.assertEqual(classify_playback_type('ci_runner'), 'video')

    def test_unknown_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            classify_playback_type('unknown_type')

    def test_empty_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            classify_playback_type('')

    def test_case_sensitive(self):
        """Trigger types are case-sensitive — 'ondemand' is not valid"""
        with self.assertRaises(ValueError):
            classify_playback_type('ondemand')


if __name__ == '__main__':
    unittest.main()
