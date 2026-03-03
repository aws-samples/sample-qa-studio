"""Unit tests for generate_execution_artifact_url Lambda function"""
import unittest
import json
import os
from unittest.mock import patch, MagicMock
from generate_execution_artifact_url import (
    handler, 
    sanitize_filename,
    sanitize_path,
    validate_content_type
)


class TestGenerateExecutionArtifactUrl(unittest.TestCase):
    """Test execution-level artifact URL generation"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['BUCKET_NAME'] = 'test-bucket'
        
    @patch('generate_execution_artifact_url.get_s3_client')
    @patch('generate_execution_artifact_url.get_dynamodb_client')
    def test_generate_url_for_recording(self, mock_get_dynamodb, mock_get_s3):
        """Verify presigned URL generated for recording artifact"""
        # Setup mocks
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'USECASE_EXECUTION#usecase-123'},
                'sk': {'S': 'EXECUTION#execution-456'}
            }
        }
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test-bucket/usecase-123/execution-456/recording.webm?signature=xyz'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456'
            },
            'body': json.dumps({
                'type': 'recording',
                'filename': 'recording.webm',
                'content_type': 'video/webm'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertIn('artifact_id', body)
        self.assertIn('upload_url', body)
        self.assertEqual(body['expires_in'], 3600)
        self.assertEqual(body['s3_key'], 'usecase-123/execution-456/recording.webm')
        
        # Verify DynamoDB put_item was called
        mock_dynamodb.put_item.assert_called_once()
        put_call = mock_dynamodb.put_item.call_args[1]
        item = put_call['Item']
        self.assertEqual(item['type']['S'], 'recording')
        self.assertEqual(item['upload_status']['S'], 'pending')
        self.assertNotIn('step_id', item)
    
    @patch('generate_execution_artifact_url.get_s3_client')
    @patch('generate_execution_artifact_url.get_dynamodb_client')
    def test_generate_url_for_logs(self, mock_get_dynamodb, mock_get_s3):
        """Verify presigned URL generated for logs artifact"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'USECASE_EXECUTION#usecase-123'},
                'sk': {'S': 'EXECUTION#execution-456'}
            }
        }
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test-bucket/key?sig=xyz'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456'
            },
            'body': json.dumps({
                'type': 'logs',
                'filename': 'logs.txt',
                'content_type': 'text/plain'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertIn('artifact_id', body)
        self.assertIn('upload_url', body)
    
    @patch('generate_execution_artifact_url.get_s3_client')
    @patch('generate_execution_artifact_url.get_dynamodb_client')
    def test_execution_not_found_returns_404(self, mock_get_dynamodb, mock_get_s3):
        """Verify 404 when execution doesn't exist"""
        mock_dynamodb = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_dynamodb.get_item.return_value = {}  # No Item
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'non-existent'
            },
            'body': json.dumps({
                'type': 'recording',
                'filename': 'test.webm',
                'content_type': 'video/webm'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertIn('Execution not found', body['error'])
    
    def test_invalid_artifact_type_returns_400(self):
        """Verify 400 when artifact type is invalid"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456'
            },
            'body': json.dumps({
                'type': 'invalid-type',
                'filename': 'test.webm',
                'content_type': 'video/webm'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Invalid artifact type', body['error'])
    
    def test_missing_filename_returns_400(self):
        """Verify 400 when filename is missing"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456'
            },
            'body': json.dumps({
                'type': 'recording',
                'content_type': 'video/webm'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Missing required fields', body['error'])
    
    def test_insufficient_permissions_returns_403(self):
        """Verify 403 when api/executions.write scope missing"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456'
            },
            'body': json.dumps({
                'type': 'recording',
                'filename': 'test.webm',
                'content_type': 'video/webm'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/usecases.read'  # Wrong scope
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])
    
    @patch('generate_execution_artifact_url.get_s3_client')
    @patch('generate_execution_artifact_url.get_dynamodb_client')
    def test_generate_url_for_trace(self, mock_get_dynamodb, mock_get_s3):
        """Verify presigned URL generated for trace artifact (Nova Act HTML logs)"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'USECASE_EXECUTION#usecase-123'},
                'sk': {'S': 'EXECUTION#execution-456'}
            }
        }
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test-bucket/key?sig=xyz'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456'
            },
            'body': json.dumps({
                'type': 'trace',
                'filename': 'trace.html',
                'content_type': 'text/html'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertIn('artifact_id', body)
        self.assertIn('upload_url', body)
        self.assertEqual(body['s3_key'], 'usecase-123/execution-456/trace.html')
        
        # Verify DynamoDB record has correct type
        put_call = mock_dynamodb.put_item.call_args[1]
        item = put_call['Item']
        self.assertEqual(item['type']['S'], 'trace')
    
    @patch('generate_execution_artifact_url.get_s3_client')
    @patch('generate_execution_artifact_url.get_dynamodb_client')
    def test_generate_url_for_trace_with_path(self, mock_get_dynamodb, mock_get_s3):
        """Verify presigned URL preserves directory structure when path is provided"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'USECASE_EXECUTION#usecase-123'},
                'sk': {'S': 'EXECUTION#execution-456'}
            }
        }
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/test-bucket/key?sig=xyz'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456'
            },
            'body': json.dumps({
                'type': 'trace',
                'filename': 'act_789_Click_button.json',
                'content_type': 'application/json',
                'path': 'session-abc/act_789_Click_button.json'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['s3_key'], 'usecase-123/execution-456/session-abc/act_789_Click_button.json')


class TestUtilityFunctions(unittest.TestCase):
    """Test utility functions"""
    
    def test_sanitize_filename_removes_path_separators(self):
        """Test filename sanitization removes path separators"""
        result = sanitize_filename('../../../etc/passwd')
        self.assertNotIn('/', result)
        self.assertNotIn('\\', result)
        # Verify path separators are replaced with underscores
        self.assertTrue('_' in result)
        self.assertTrue('etc' in result)
        self.assertTrue('passwd' in result)
    
    def test_sanitize_filename_limits_length(self):
        """Test filename sanitization limits length to 255 characters"""
        long_name = 'a' * 300 + '.txt'
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 255)
        self.assertTrue(result.endswith('.txt'))
    
    def test_validate_content_type_accepts_valid_types(self):
        """Test content type validation accepts valid types"""
        # Should not raise
        validate_content_type('recording', 'video/webm')
        validate_content_type('recording', 'video/mp4')
        validate_content_type('logs', 'text/plain')
        validate_content_type('trace', 'text/html')
        validate_content_type('trace', 'application/json')
    
    def test_validate_content_type_rejects_invalid_types(self):
        """Test content type validation rejects invalid types"""
        with self.assertRaises(ValueError):
            validate_content_type('recording', 'text/plain')
        
        with self.assertRaises(ValueError):
            validate_content_type('logs', 'video/webm')
        
        with self.assertRaises(ValueError):
            validate_content_type('trace', 'text/plain')
    
    def test_sanitize_path_preserves_directory_structure(self):
        """Test path sanitization preserves nested directories"""
        result = sanitize_path('session-123/act_456_Click_button.html')
        self.assertEqual(result, 'session-123/act_456_Click_button.html')
    
    def test_sanitize_path_removes_traversal(self):
        """Test path sanitization removes .. components"""
        result = sanitize_path('../../etc/passwd')
        self.assertEqual(result, 'etc/passwd')
    
    def test_sanitize_path_removes_leading_slashes(self):
        """Test path sanitization removes leading slashes"""
        result = sanitize_path('/session-123/trace.html')
        self.assertEqual(result, 'session-123/trace.html')
    
    def test_sanitize_path_normalizes_backslashes(self):
        """Test path sanitization normalizes backslashes to forward slashes"""
        result = sanitize_path('session-123\\trace.html')
        self.assertEqual(result, 'session-123/trace.html')
    
    def test_sanitize_path_removes_null_bytes(self):
        """Test path sanitization removes null bytes"""
        result = sanitize_path('session\0-123/trace.html')
        self.assertEqual(result, 'session-123/trace.html')


if __name__ == '__main__':
    unittest.main()
