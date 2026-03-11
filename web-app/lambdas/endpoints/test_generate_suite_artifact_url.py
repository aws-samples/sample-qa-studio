"""
Unit tests and property-based tests for generate_suite_artifact_url Lambda function.

Feature: runner-log-capture
"""
import unittest
import json
import os
from unittest.mock import patch, MagicMock

from hypothesis import given, strategies as st, settings, assume

from generate_suite_artifact_url import (
    handler,
    sanitize_filename,
    generate_s3_key,
)


# ---------------------------------------------------------------------------
# Strategies for property-based tests
# ---------------------------------------------------------------------------

# Valid UUID strategy for path parameter IDs
id_strategy = st.uuids().map(str)

# Filenames without path separators or null bytes
safe_filename_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='-_.',
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() and not s.startswith('.'))


# ---------------------------------------------------------------------------
# Property 5: Suite artifact S3 key format
# Feature: runner-log-capture, Property 5: Suite artifact S3 key format
# ---------------------------------------------------------------------------
class TestSuiteArtifactS3KeyProperty(unittest.TestCase):
    """**Validates: Requirements 4.2**"""

    @given(
        suite_id=id_strategy,
        suite_execution_id=id_strategy,
        filename=safe_filename_strategy,
    )
    @settings(max_examples=100)
    def test_s3_key_matches_expected_format(self, suite_id, suite_execution_id, filename):
        """For any valid suite_id, suite_execution_id, and filename,
        the S3 key must match suites/{suite_id}/{suite_execution_id}/{filename}."""
        key = generate_s3_key(suite_id, suite_execution_id, filename)

        # Filename is sanitized (no / or \ or \0), so the sanitized version
        # should be used in the key.
        sanitized = sanitize_filename(filename)
        expected = f'suites/{suite_id}/{suite_execution_id}/{sanitized}'
        self.assertEqual(key, expected)

        # Key must start with 'suites/'
        self.assertTrue(key.startswith('suites/'))

        # Key must contain exactly 3 slashes after the prefix
        parts = key.split('/')
        self.assertEqual(parts[0], 'suites')
        self.assertEqual(parts[1], suite_id)
        self.assertEqual(parts[2], suite_execution_id)
        self.assertEqual(parts[3], sanitized)


# ---------------------------------------------------------------------------
# Property 6: Suite artifact upload endpoint response completeness
# Feature: runner-log-capture, Property 6: Suite artifact upload endpoint response completeness
# ---------------------------------------------------------------------------
class TestSuiteArtifactResponseCompletenessProperty(unittest.TestCase):
    """**Validates: Requirements 4.1, 4.3**"""

    @given(
        suite_id=id_strategy,
        execution_id=id_strategy,
        filename=safe_filename_strategy,
    )
    @settings(max_examples=100)
    @patch('generate_suite_artifact_url.get_s3_client')
    @patch('generate_suite_artifact_url.get_dynamodb_client')
    def test_valid_request_returns_complete_response(
        self, mock_get_dynamodb, mock_get_s3, suite_id, execution_id, filename
    ):
        """For any valid request, the response must contain upload_url (HTTPS),
        expires_in, and s3_key."""
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['BUCKET_NAME'] = 'test-bucket'

        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': f'SUITE_EXECUTION#{suite_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'},
            }
        }
        mock_s3.generate_presigned_url.return_value = (
            f'https://s3.amazonaws.com/test-bucket/suites/{suite_id}/{execution_id}/{filename}'
        )

        event = {
            'pathParameters': {
                'suite_id': suite_id,
                'execution_id': execution_id,
            },
            'body': json.dumps({
                'type': 'logs',
                'filename': filename,
                'content_type': 'text/plain',
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/suite.write',
                }
            },
        }

        response = handler(event, None)
        self.assertEqual(response['statusCode'], 200)

        body = json.loads(response['body'])

        # Must contain all three required fields
        self.assertIn('upload_url', body)
        self.assertIn('expires_in', body)
        self.assertIn('s3_key', body)

        # upload_url must be HTTPS
        self.assertTrue(body['upload_url'].startswith('https://'))

        # expires_in must be a positive integer
        self.assertIsInstance(body['expires_in'], int)
        self.assertGreater(body['expires_in'], 0)

        # s3_key must follow the suite artifact format
        self.assertTrue(body['s3_key'].startswith('suites/'))

        # Must NOT contain artifact_id (no DynamoDB record)
        self.assertNotIn('artifact_id', body)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
class TestGenerateSuiteArtifactUrl(unittest.TestCase):
    """Unit tests for the suite artifact URL generation endpoint."""

    def setUp(self):
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['BUCKET_NAME'] = 'test-bucket'

    # --- 6.4: test_handler_success ---
    @patch('generate_suite_artifact_url.get_s3_client')
    @patch('generate_suite_artifact_url.get_dynamodb_client')
    def test_handler_success(self, mock_get_dynamodb, mock_get_s3):
        """Valid request returns 200 with presigned URL, expires_in, and s3_key."""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'SUITE_EXECUTION#suite-123'},
                'sk': {'S': 'EXECUTION#exec-456'},
            }
        }
        mock_s3.generate_presigned_url.return_value = (
            'https://s3.amazonaws.com/test-bucket/suites/suite-123/exec-456/suite_logs.txt?sig=xyz'
        )

        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456',
            },
            'body': json.dumps({
                'type': 'logs',
                'filename': 'suite_logs.txt',
                'content_type': 'text/plain',
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/suite.write',
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertIn('upload_url', body)
        self.assertEqual(body['expires_in'], 3600)
        self.assertEqual(body['s3_key'], 'suites/suite-123/exec-456/suite_logs.txt')
        # No artifact_id — no DynamoDB record
        self.assertNotIn('artifact_id', body)

    # --- 6.4: test_handler_missing_fields_returns_400 ---
    def test_handler_missing_fields_returns_400(self):
        """Missing type/filename/content_type returns 400."""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456',
            },
            'body': json.dumps({
                'type': 'logs',
                # filename and content_type missing
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/suite.write',
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Missing required fields', body['error'])

    # --- 6.4: test_handler_missing_scope_returns_403 ---
    def test_handler_missing_scope_returns_403(self):
        """Missing api/suite.write scope returns 403."""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456',
            },
            'body': json.dumps({
                'type': 'logs',
                'filename': 'suite_logs.txt',
                'content_type': 'text/plain',
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/usecases.read',  # Wrong scope
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])

    # --- 6.4: test_handler_suite_execution_not_found_returns_404 ---
    @patch('generate_suite_artifact_url.get_s3_client')
    @patch('generate_suite_artifact_url.get_dynamodb_client')
    def test_handler_suite_execution_not_found_returns_404(self, mock_get_dynamodb, mock_get_s3):
        """Nonexistent suite execution returns 404."""
        mock_dynamodb = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_dynamodb.get_item.return_value = {}  # No Item

        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'non-existent',
            },
            'body': json.dumps({
                'type': 'logs',
                'filename': 'suite_logs.txt',
                'content_type': 'text/plain',
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/suite.write',
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertIn('Suite execution not found', body['error'])

    # --- 6.4: test_no_dynamodb_artifact_record_created ---
    @patch('generate_suite_artifact_url.get_s3_client')
    @patch('generate_suite_artifact_url.get_dynamodb_client')
    def test_no_dynamodb_artifact_record_created(self, mock_get_dynamodb, mock_get_s3):
        """Verify no DynamoDB put_item is called — no artifact record created."""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3

        mock_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'SUITE_EXECUTION#suite-123'},
                'sk': {'S': 'EXECUTION#exec-456'},
            }
        }
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test-bucket/key?sig=xyz'

        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456',
            },
            'body': json.dumps({
                'type': 'logs',
                'filename': 'suite_logs.txt',
                'content_type': 'text/plain',
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/suite.write',
                }
            },
        }

        response = handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        # DynamoDB get_item is called to validate execution exists,
        # but put_item must NOT be called (no artifact record).
        mock_dynamodb.put_item.assert_not_called()


class TestSuiteArtifactUtilityFunctions(unittest.TestCase):
    """Unit tests for utility functions."""

    def test_sanitize_filename_removes_path_separators(self):
        result = sanitize_filename('../../../etc/passwd')
        self.assertNotIn('/', result)
        self.assertNotIn('\\', result)

    def test_sanitize_filename_limits_length(self):
        long_name = 'a' * 300 + '.txt'
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 255)
        self.assertTrue(result.endswith('.txt'))

    def test_generate_s3_key_format(self):
        key = generate_s3_key('suite-abc', 'exec-123', 'suite_logs.txt')
        self.assertEqual(key, 'suites/suite-abc/exec-123/suite_logs.txt')

    def test_generate_s3_key_sanitizes_filename(self):
        key = generate_s3_key('suite-abc', 'exec-123', '../evil.txt')
        # Path separators are replaced with underscores, preventing traversal
        self.assertEqual(key, 'suites/suite-abc/exec-123/.._evil.txt')
        self.assertTrue(key.startswith('suites/suite-abc/exec-123/'))


if __name__ == '__main__':
    unittest.main()
