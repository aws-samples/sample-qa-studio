"""
Unit tests and property-based tests for list_suite_artifacts Lambda function.

Feature: runner-log-capture
"""
import unittest
import json
import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from botocore.exceptions import ClientError
from hypothesis import given, strategies as st, settings

from list_suite_artifacts import (
    handler,
    infer_type_and_content_type,
)


# ---------------------------------------------------------------------------
# Strategies for property-based tests
# ---------------------------------------------------------------------------

# Valid UUID strategy for path parameter IDs
id_strategy = st.uuids().map(str)

# Filenames with known extensions for type inference
known_extensions = ['.txt', '.webm', '.mp4', '.json', '.png']
safe_filename_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='-_',
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

filename_with_ext_strategy = st.tuples(
    safe_filename_strategy,
    st.sampled_from(known_extensions),
).map(lambda t: t[0] + t[1])


# ---------------------------------------------------------------------------
# Property 7: Suite artifact list via S3 discovery
# Feature: runner-log-capture, Property 7: Suite artifact list via S3 discovery
# ---------------------------------------------------------------------------
class TestSuiteArtifactListProperty(unittest.TestCase):
    """**Validates: Requirements 6.6**"""

    @given(
        suite_id=id_strategy,
        execution_id=id_strategy,
        filenames=st.lists(filename_with_ext_strategy, min_size=0, max_size=10, unique=True),
    )
    @settings(max_examples=100)
    @patch('list_suite_artifacts.get_s3_client')
    def test_list_returns_exactly_n_artifacts_with_all_fields(
        self, mock_get_s3, suite_id, execution_id, filenames
    ):
        """For any N S3 objects under prefix, list returns exactly N artifacts
        with all required fields: filename, type, content_type, download_url, size, last_modified."""
        os.environ['BUCKET_NAME'] = 'test-bucket'

        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        prefix = f'suites/{suite_id}/{execution_id}/'
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # Build mock S3 Contents
        contents = []
        for fname in filenames:
            contents.append({
                'Key': f'{prefix}{fname}',
                'Size': 1024,
                'LastModified': now,
            })

        mock_s3.list_objects_v2.return_value = {
            'Contents': contents,
        } if contents else {}

        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test-bucket/key?sig=abc'

        event = {
            'pathParameters': {
                'suite_id': suite_id,
                'execution_id': execution_id,
            },
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/suite.read',
                }
            },
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)

        body = json.loads(response['body'])
        artifacts = body['artifacts']

        # Exactly N artifacts returned
        self.assertEqual(len(artifacts), len(filenames))

        # Each artifact has all required fields
        required_fields = {'filename', 'type', 'content_type', 'download_url', 'size', 'last_modified'}
        for artifact in artifacts:
            self.assertTrue(
                required_fields.issubset(artifact.keys()),
                f'Missing fields: {required_fields - artifact.keys()}',
            )
            # download_url must be HTTPS
            self.assertTrue(artifact['download_url'].startswith('https://'))
            # size must be non-negative
            self.assertGreaterEqual(artifact['size'], 0)
            # filename must not be empty
            self.assertTrue(len(artifact['filename']) > 0)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
class TestListSuiteArtifacts(unittest.TestCase):
    """Unit tests for the suite artifact list endpoint."""

    def setUp(self):
        os.environ['BUCKET_NAME'] = 'test-bucket'

    # --- 7.3: test_handler_success ---
    @patch('list_suite_artifacts.get_s3_client')
    def test_handler_success(self, mock_get_s3):
        """Returns artifacts with download URLs from S3 ListObjectsV2."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'suites/suite-123/exec-456/suite_logs.txt',
                    'Size': 2048,
                    'LastModified': now,
                },
                {
                    'Key': 'suites/suite-123/exec-456/recording.webm',
                    'Size': 5242880,
                    'LastModified': now,
                },
            ]
        }
        mock_s3.generate_presigned_url.return_value = (
            'https://s3.amazonaws.com/test-bucket/key?sig=abc'
        )

        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456',
            },
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/suite.read',
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(len(body['artifacts']), 2)

        logs_artifact = body['artifacts'][0]
        self.assertEqual(logs_artifact['filename'], 'suite_logs.txt')
        self.assertEqual(logs_artifact['type'], 'logs')
        self.assertEqual(logs_artifact['content_type'], 'text/plain')
        self.assertTrue(logs_artifact['download_url'].startswith('https://'))
        self.assertEqual(logs_artifact['size'], 2048)

        recording_artifact = body['artifacts'][1]
        self.assertEqual(recording_artifact['filename'], 'recording.webm')
        self.assertEqual(recording_artifact['type'], 'recording')
        self.assertEqual(recording_artifact['content_type'], 'video/webm')

    # --- 7.3: test_handler_empty_results ---
    @patch('list_suite_artifacts.get_s3_client')
    def test_handler_empty_results(self, mock_get_s3):
        """No S3 objects returns empty artifacts array."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        # No Contents key in response
        mock_s3.list_objects_v2.return_value = {}

        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456',
            },
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/suite.read',
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['artifacts'], [])

    # --- 7.3: test_handler_missing_scope_returns_403 ---
    def test_handler_missing_scope_returns_403(self):
        """Missing api/suite.read scope returns 403."""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456',
            },
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/usecases.read',  # Wrong scope
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])

    # --- 7.3: test_handler_infers_type_from_filename ---
    def test_handler_infers_type_from_filename(self):
        """Verify filename-to-type mapping: .txt → logs, .webm → recording, .mp4 → recording, other → unknown."""
        # .txt → logs
        artifact_type, content_type = infer_type_and_content_type('suite_logs.txt')
        self.assertEqual(artifact_type, 'logs')
        self.assertEqual(content_type, 'text/plain')

        # .webm → recording
        artifact_type, content_type = infer_type_and_content_type('recording.webm')
        self.assertEqual(artifact_type, 'recording')
        self.assertEqual(content_type, 'video/webm')

        # .mp4 → recording
        artifact_type, content_type = infer_type_and_content_type('video.mp4')
        self.assertEqual(artifact_type, 'recording')
        self.assertEqual(content_type, 'video/mp4')

        # unknown extension → unknown
        artifact_type, content_type = infer_type_and_content_type('data.bin')
        self.assertEqual(artifact_type, 'unknown')
        self.assertEqual(content_type, 'application/octet-stream')

    # --- 7.3: test_handler_s3_list_failure_returns_500 ---
    @patch('list_suite_artifacts.get_s3_client')
    def test_handler_s3_list_failure_returns_500(self, mock_get_s3):
        """S3 ListObjectsV2 failure returns 500."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        mock_s3.list_objects_v2.side_effect = ClientError(
            {'Error': {'Code': 'InternalError', 'Message': 'S3 failure'}},
            'ListObjectsV2',
        )

        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456',
            },
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/suite.read',
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertIn('Failed to list artifacts', body['error'])


if __name__ == '__main__':
    unittest.main()
