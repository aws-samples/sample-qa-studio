import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from create_test_suite import handler


class TestCreateTestSuite(unittest.TestCase):
    """Test suite for create_test_suite Lambda function"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        
    def test_create_suite_success(self):
        """Test successful test suite creation"""
        # Mock event
        event = {
            'body': json.dumps({
                'name': 'Smoke Tests',
                'description': 'Critical path smoke tests',
                'scope': 'suite:smoke-tests',
                'tags': ['smoke', 'critical']
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        # Mock DynamoDB
        with patch('create_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            # Call handler
            response = handler(event, None)
            
            # Verify response
            self.assertEqual(response['statusCode'], 201)
            body = json.loads(response['body'])
            self.assertEqual(body['name'], 'Smoke Tests')
            self.assertEqual(body['description'], 'Critical path smoke tests')
            self.assertEqual(body['scope'], 'suite:smoke-tests')
            self.assertEqual(body['tags'], ['smoke', 'critical'])
            self.assertIn('id', body)
            self.assertIn('created_at', body)
            self.assertEqual(body['total_usecases'], 0)
            self.assertEqual(body['schedule_enabled'], False)
            
            # Verify DynamoDB was called
            mock_table.put_item.assert_called_once()
    
    def test_create_suite_with_schedule(self):
        """Test creating suite with schedule configuration"""
        event = {
            'body': json.dumps({
                'name': 'Nightly Tests',
                'description': 'Tests that run nightly',
                'scope': 'suite:nightly',
                'tags': ['nightly'],
                'schedule_enabled': True,
                'schedule_expression': '0 2 * * *',
                'schedule_timezone': 'UTC'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('create_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 201)
            body = json.loads(response['body'])
            self.assertEqual(body['schedule_enabled'], True)
            self.assertEqual(body['schedule_expression'], '0 2 * * *')
            self.assertEqual(body['schedule_timezone'], 'UTC')
    
    def test_missing_name(self):
        """Test that missing name returns 400"""
        event = {
            'body': json.dumps({
                'description': 'Test description',
                'scope': 'suite:test'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('name is required', body['error'])
    
    def test_name_too_short(self):
        """Test that name shorter than 3 characters returns 400"""
        event = {
            'body': json.dumps({
                'name': 'AB',
                'description': 'Test description',
                'scope': 'suite:test'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('between 3 and 100 characters', body['error'])
    
    def test_name_too_long(self):
        """Test that name longer than 100 characters returns 400"""
        event = {
            'body': json.dumps({
                'name': 'A' * 101,
                'description': 'Test description',
                'scope': 'suite:test'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('between 3 and 100 characters', body['error'])
    
    def test_missing_description(self):
        """Test that missing description returns 400"""
        event = {
            'body': json.dumps({
                'name': 'Test Suite',
                'scope': 'suite:test'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('description is required', body['error'])
    
    def test_description_too_long(self):
        """Test that description longer than 500 characters returns 400"""
        event = {
            'body': json.dumps({
                'name': 'Test Suite',
                'description': 'A' * 501,
                'scope': 'suite:test'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('500 characters or less', body['error'])
    
    def test_missing_scope_auto_generates(self):
        """Test that missing scope auto-generates from name"""
        event = {
            'body': json.dumps({
                'name': 'Test Suite',
                'description': 'Test description'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        with patch('create_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 201)
            body = json.loads(response['body'])
            self.assertEqual(body['scope'], 'suite:test-suite')
    
    def test_invalid_scope_format(self):
        """Test that scope not starting with 'suite:' returns 400"""
        event = {
            'body': json.dumps({
                'name': 'Test Suite',
                'description': 'Test description',
                'scope': 'invalid:scope'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('must start with "suite:"', body['error'])
    
    def test_invalid_tags_type(self):
        """Test that non-array tags returns 400"""
        event = {
            'body': json.dumps({
                'name': 'Test Suite',
                'description': 'Test description',
                'scope': 'suite:test',
                'tags': 'not-an-array'
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('tags must be an array', body['error'])
    
    def test_insufficient_api_scope(self):
        """Test that missing api/suite.write scope returns 403"""
        event = {
            'body': json.dumps({
                'name': 'Test Suite',
                'description': 'Test description',
                'scope': 'suite:test',
                'tags': []
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/usecases.read'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])
    
    def test_insufficient_suite_scope(self):
        """Test removed - no longer using per-suite scope validation"""
        pass
    
    def test_admin_scope_grants_access(self):
        """Test that api/admin scope grants access"""
        event = {
            'body': json.dumps({
                'name': 'Test Suite',
                'description': 'Test description',
                'scope': 'suite:test',
                'tags': []
            }),
            'requestContext': {
                'authorizer': {
                    'email': 'admin@example.com',
                    'sub': 'admin-123',
                    'scope': 'api/admin'
                }
            }
        }
        
        with patch('create_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 201)
    
    def test_wildcard_suite_scope_grants_access(self):
        """Test removed - no longer using per-suite scope validation"""
        pass
    
    def test_invalid_json(self):
        """Test that invalid JSON returns 400"""
        event = {
            'body': 'not valid json',
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Invalid JSON', body['error'])


if __name__ == '__main__':
    unittest.main()
