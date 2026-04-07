"""Unit tests for get_recording_data lambda."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

os.environ.setdefault('TABLE_NAME', 'test-table')
os.environ.setdefault('BUCKET_NAME', 'test-bucket')

from get_recording_data import handler


def _make_event(session_id='sess-123', usecase_id='uc-456'):
    """Build a minimal API Gateway event."""
    return {
        'pathParameters': {'sessionId': session_id},
        'queryStringParameters': {'usecaseId': usecase_id},
        'requestContext': {
            'authorizer': {
                'scope': 'api/usecases.write',
            }
        },
    }


SAMPLE_RECORDING_DATA = {
    'type': 'cdp_actions',
    'version': '1.0',
    'data': {
        'session': {
            'id': 'abc',
            'startedAt': 1000,
            'stoppedAt': 2000,
            'tabId': 0,
            'startingUrl': 'https://example.com',
            'actions': [],
        },
        'event_count': 0,
        'duration_seconds': 1.0,
    },
    'captured_at': '2026-03-11T00:00:00+00:00',
}


class TestGetRecordingData:
    """Tests for the get_recording_data handler."""

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_returns_available_when_completed(self, mock_scopes, mock_boto3):
        """Completed recording with valid S3 data returns status=available."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        s3_key = 'uc-456/sess-123/recording_data.json'

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'recording_status': 'completed',
                'recording_s3_key': s3_key,
            }
        }

        # Mock S3 client to return recording data
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client
        mock_s3_body = MagicMock()
        mock_s3_body.read.return_value = json.dumps(SAMPLE_RECORDING_DATA).encode('utf-8')
        mock_s3_client.get_object.return_value = {'Body': mock_s3_body}

        response = handler(_make_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'available'
        assert body['recording_data'] is not None

        # Verify S3 was called with correct params
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='test-bucket', Key=s3_key
        )

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_returns_not_available_when_recording(self, mock_scopes, mock_boto3):
        """In-progress recording returns status=not_available."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'recording_status': 'recording',
            }
        }

        response = handler(_make_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'not_available'
        assert body['recording_data'] is None

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_returns_error_when_worker_error(self, mock_scopes, mock_boto3):
        """Worker error status is surfaced as status=error with message."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'recording_status': 'error',
                'recording_error': 'CDP session lost',
            }
        }

        response = handler(_make_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'error'
        assert body['error'] == 'CDP session lost'
        assert body['recording_data'] is None

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_returns_error_with_default_message(self, mock_scopes, mock_boto3):
        """Worker error without recording_error field uses default message."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'recording_status': 'error',
            }
        }

        response = handler(_make_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'error'
        assert 'failed' in body['error'].lower()

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_returns_404_when_execution_not_found(self, mock_scopes, mock_boto3):
        """Missing execution record returns 404."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        response = handler(_make_event(), None)
        assert response['statusCode'] == 404

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_returns_not_available_when_no_recording_status(self, mock_scopes, mock_boto3):
        """Execution record without recording_status returns not_available."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {}
        }

        response = handler(_make_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'not_available'

    @patch('get_recording_data.require_scopes')
    def test_missing_usecase_id_returns_400(self, mock_scopes):
        """Missing usecaseId query parameter returns 400."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        event = _make_event()
        event['queryStringParameters'] = {}

        response = handler(event, None)
        assert response['statusCode'] == 400

    @patch('get_recording_data.require_scopes')
    def test_insufficient_scope_returns_403(self, mock_scopes):
        """Insufficient scopes returns 403."""
        mock_scopes.return_value = (None, {
            'statusCode': 403,
            'body': json.dumps({'error': 'Forbidden'})
        })

        response = handler(_make_event(), None)
        assert response['statusCode'] == 403

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_s3_fetch_failure_returns_not_available(self, mock_scopes, mock_boto3):
        """S3 get_object failure returns not_available gracefully."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        s3_key = 'uc-456/sess-123/recording_data.json'

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'recording_status': 'completed',
                'recording_s3_key': s3_key,
            }
        }

        # Mock S3 client to raise an exception
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client
        mock_s3_client.get_object.side_effect = Exception('NoSuchKey: The specified key does not exist.')

        response = handler(_make_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'not_available'
        assert body['recording_data'] is None

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_malformed_s3_data_returns_not_available(self, mock_scopes, mock_boto3):
        """Completed recording with unparseable JSON in S3 returns not_available."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        s3_key = 'uc-456/sess-123/recording_data.json'

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'recording_status': 'completed',
                'recording_s3_key': s3_key,
            }
        }

        # Mock S3 client to return invalid JSON
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client
        mock_s3_body = MagicMock()
        mock_s3_body.read.return_value = b'{invalid json'
        mock_s3_client.get_object.return_value = {'Body': mock_s3_body}

        response = handler(_make_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'not_available'

    @patch('get_recording_data.boto3')
    @patch('get_recording_data.require_scopes')
    def test_completed_without_s3_key_returns_not_available(self, mock_scopes, mock_boto3):
        """Completed status but missing recording_s3_key returns not_available."""
        mock_scopes.return_value = ({'identity': 'user@example.com'}, None)

        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'recording_status': 'completed',
            }
        }

        response = handler(_make_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'not_available'
