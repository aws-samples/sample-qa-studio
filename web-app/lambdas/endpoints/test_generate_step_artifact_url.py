"""Unit tests for generate_step_artifact_url Lambda function"""
import unittest
import json
import os
from unittest.mock import patch, MagicMock
from generate_step_artifact_url import (
    handler, 
    sanitize_filename, 
    validate_content_type
)


class TestGenerateStepArtifactUrl(unittest.TestCase):
    """Test step-level artifact URL generation"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        os.environ['BUCKET_NAME'] = 'test-bucket'
    
    @patch('generate_step_artifact_url.get_s3_client')
    @patch('generate_step_artifact_url.get_dynamodb_client')
    def test_generate_url_for_screenshot(self, mock_get_dynamodb, mock_get_s3):
        """Verify presigned URL generated for screenshot"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        # Mock execution and step exist
        mock_dynamodb.get_item.return_value = {'Item': {}}
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/url'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'filename': 'screenshot.png',
                'content_type': 'image/png'
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
        self.assertIn('steps/step-789/screenshot.png', body['s3_key'])
    
    @patch('generate_step_artifact_url.get_s3_client')
    @patch('generate_step_artifact_url.get_dynamodb_client')
    def test_generate_url_for_trace(self, mock_get_dynamodb, mock_get_s3):
        """Verify presigned URL generated for trace"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        mock_dynamodb.get_item.return_value = {'Item': {}}
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/url'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'filename': 'trace.json',
                'content_type': 'application/json'
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
    
    @patch('generate_step_artifact_url.get_s3_client')
    @patch('generate_step_artifact_url.get_dynamodb_client')
    def test_artifact_record_includes_step_id(self, mock_get_dynamodb, mock_get_s3):
        """Verify artifact record includes step_id field"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        mock_dynamodb.get_item.return_value = {'Item': {}}
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/url'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'filename': 'screenshot.png',
                'content_type': 'image/png'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        handler(event, None)
        
        # Verify artifact record includes step_id
        put_call = mock_dynamodb.put_item.call_args[1]
        item = put_call['Item']
        self.assertIn('step_id', item)
        self.assertEqual(item['step_id']['S'], 'step-789')
    
    @patch('generate_step_artifact_url.get_s3_client')
    @patch('generate_step_artifact_url.get_dynamodb_client')
    def test_s3_key_includes_step_id(self, mock_get_dynamodb, mock_get_s3):
        """Verify S3 key includes step_id in path"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        mock_dynamodb.get_item.return_value = {'Item': {}}
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/url'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'filename': 'screenshot.png',
                'content_type': 'image/png'
            }),
            'requestContext': {
                'authorizer': {
                    'client_id': 'ci-runner-client',
                    'scope': 'api/executions.write'
                }
            }
        }
        
        response = handler(event, None)
        
        body = json.loads(response['body'])
        expected_key = 'usecase-123/execution-456/steps/step-789/screenshot.png'
        self.assertEqual(body['s3_key'], expected_key)
    
    @patch('generate_step_artifact_url.get_dynamodb_client')
    def test_step_not_found_returns_404(self, mock_get_dynamodb):
        """Verify 404 when step doesn't exist"""
        mock_dynamodb = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # First call for execution (exists), second call for step (doesn't exist)
        mock_dynamodb.get_item.side_effect = [
            {'Item': {}},  # Execution exists
            {}  # Step doesn't exist
        ]
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'non-existent'
            },
            'body': json.dumps({
                'filename': 'screenshot.png',
                'content_type': 'image/png'
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
        self.assertIn('Step not found', body['error'])
    
    def test_missing_step_id_returns_400(self):
        """Verify 400 when step_id is missing"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456'
                # Missing stepId
            },
            'body': json.dumps({
                'filename': 'screenshot.png',
                'content_type': 'image/png'
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
        self.assertIn('Missing required path parameters', body['error'])
    
    def test_invalid_content_type_returns_400(self):
        """Verify 400 when content type is invalid"""
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
                'filename': 'file.txt',
                'content_type': 'text/plain'  # Not allowed for step artifacts
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
        self.assertIn('Invalid content type', body['error'])
    
    @patch('generate_step_artifact_url.get_s3_client')
    @patch('generate_step_artifact_url.get_dynamodb_client')
    def test_generate_url_for_html_trace(self, mock_get_dynamodb, mock_get_s3):
        """Verify presigned URL generated for HTML trace file"""
        mock_dynamodb = MagicMock()
        mock_s3 = MagicMock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_get_s3.return_value = mock_s3
        
        mock_dynamodb.get_item.return_value = {'Item': {}}
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/url'
        
        event = {
            'pathParameters': {
                'id': 'usecase-123',
                'executionId': 'execution-456',
                'stepId': 'step-789'
            },
            'body': json.dumps({
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
        self.assertEqual(body['s3_key'], 'usecase-123/execution-456/steps/step-789/trace.html')
        
        # Verify artifact type is 'trace' for text/html
        put_call = mock_dynamodb.put_item.call_args[1]
        item = put_call['Item']
        self.assertEqual(item['type']['S'], 'trace')


class TestStepArtifactUtilities(unittest.TestCase):
    """Test utility functions for step artifacts"""
    
    def test_validate_content_type_accepts_images(self):
        """Test content type validation accepts image types"""
        # Should not raise
        validate_content_type('image/png')
        validate_content_type('image/jpeg')
    
    def test_validate_content_type_accepts_json(self):
        """Test content type validation accepts JSON"""
        # Should not raise
        validate_content_type('application/json')
    
    def test_validate_content_type_accepts_html(self):
        """Test content type validation accepts HTML for trace files"""
        # Should not raise
        validate_content_type('text/html')
    
    def test_validate_content_type_rejects_invalid(self):
        """Test content type validation rejects invalid types"""
        with self.assertRaises(ValueError):
            validate_content_type('text/plain')
        
        with self.assertRaises(ValueError):
            validate_content_type('video/webm')


if __name__ == '__main__':
    unittest.main()
