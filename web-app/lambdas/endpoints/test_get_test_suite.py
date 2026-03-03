import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from get_test_suite import handler


class TestGetTestSuite(unittest.TestCase):
    """Test suite for get_test_suite Lambda function"""
    
    def setUp(self):
        """Set up test fixtures"""
        os.environ['TABLE_NAME'] = 'test-table'
        
    def test_get_suite_success(self):
        """Test successful test suite retrieval"""
        # Mock event
        event = {
            'pathParameters': {
                'suite_id': 'suite-123'
            },
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.read'
                }
            }
        }
        
        # Mock DynamoDB response
        mock_suite = {
            'pk': 'TEST_SUITES',
            'sk': 'SUITE#suite-123',
            'id': 'suite-123',
            'name': 'Smoke Tests',
            'description': 'Critical path smoke tests',
            'scope': 'suite:smoke-tests',
            'tags': ['smoke', 'critical'],
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
            'created_by': 'user-123',
            'schedule_enabled': False,
            'total_usecases': 5,
            'last_execution_id': 'exec-456',
            'last_execution_status': 'completed',
            'last_execution_time': '2024-01-02T00:00:00Z',
            'last_successful_count': 4
        }
        
        # Mock DynamoDB
        with patch('get_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {'Item': mock_suite}
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            # Call handler
            response = handler(event, None)
            
            # Verify response
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['id'], 'suite-123')
            self.assertEqual(body['name'], 'Smoke Tests')
            self.assertEqual(body['description'], 'Critical path smoke tests')
            self.assertEqual(body['scope'], 'suite:smoke-tests')
            self.assertEqual(body['tags'], ['smoke', 'critical'])
            self.assertEqual(body['total_usecases'], 5)
            self.assertEqual(body['last_execution_status'], 'completed')
            self.assertEqual(body['last_successful_count'], 4)
            
            # Verify pk/sk are not in response
            self.assertNotIn('pk', body)
            self.assertNotIn('sk', body)
            
            # Verify DynamoDB was called correctly
            mock_table.get_item.assert_called_once_with(
                Key={
                    'pk': 'TEST_SUITES',
                    'sk': 'SUITE#suite-123'
                }
            )
    
    def test_get_suite_with_schedule(self):
        """Test retrieving suite with schedule configuration"""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123'
            },
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.read'
                }
            }
        }
        
        mock_suite = {
            'pk': 'TEST_SUITES',
            'sk': 'SUITE#suite-123',
            'id': 'suite-123',
            'name': 'Nightly Tests',
            'description': 'Tests that run nightly',
            'scope': 'suite:nightly',
            'tags': ['nightly'],
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
            'created_by': 'user-123',
            'schedule_enabled': True,
            'schedule_expression': '0 2 * * *',
            'schedule_timezone': 'UTC',
            'total_usecases': 10
        }
        
        with patch('get_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {'Item': mock_suite}
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
            body = json.loads(response['body'])
            self.assertEqual(body['schedule_enabled'], True)
            self.assertEqual(body['schedule_expression'], '0 2 * * *')
            self.assertEqual(body['schedule_timezone'], 'UTC')
    
    def test_missing_suite_id(self):
        """Test that missing suite_id returns 400"""
        event = {
            'pathParameters': {},
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.read'
                }
            }
        }
        
        response = handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('suite_id is required', body['error'])
    
    def test_suite_not_found(self):
        """Test that non-existent suite returns 404"""
        event = {
            'pathParameters': {
                'suite_id': 'nonexistent-suite'
            },
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.read'
                }
            }
        }
        
        with patch('get_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}  # No Item in response
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 404)
            body = json.loads(response['body'])
            self.assertIn('Test suite not found', body['error'])
    
    def test_insufficient_api_scope(self):
        """Test that missing api/suite.read scope returns 403"""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123'
            },
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
        """Test that api/admin scope grants access to any suite"""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123'
            },
            'requestContext': {
                'authorizer': {
                    'email': 'admin@example.com',
                    'sub': 'admin-123',
                    'scope': 'api/admin'
                }
            }
        }
        
        mock_suite = {
            'pk': 'TEST_SUITES',
            'sk': 'SUITE#suite-123',
            'id': 'suite-123',
            'name': 'Test Suite',
            'description': 'Test description',
            'scope': 'suite:any-suite',
            'tags': [],
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
            'created_by': 'user-123',
            'schedule_enabled': False,
            'total_usecases': 0
        }
        
        with patch('get_test_suite.boto3') as mock_boto3:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {'Item': mock_suite}
            mock_boto3.resource.return_value.Table.return_value = mock_table
            
            response = handler(event, None)
            
            self.assertEqual(response['statusCode'], 200)
    
    def test_wildcard_suite_scope_grants_access(self):
        """Test removed - no longer using per-suite scope validation"""
        pass
    
    def test_write_permission_implies_read(self):
        """Test removed - no longer using per-suite scope validation"""
        pass


if __name__ == '__main__':
    unittest.main()
