import json
import unittest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError
import delete_test_suite


class TestDeleteTestSuite(unittest.TestCase):
    """Unit tests for delete_test_suite Lambda function"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.suite_id = '01234567-89ab-cdef-0123-456789abcdef'
        self.user_identity = 'test@example.com'
        self.suite_scope = 'suite:smoke-tests'
        
        # Mock suite item
        self.mock_suite = {
            'pk': 'TEST_SUITES',
            'sk': f'SUITE#{self.suite_id}',
            'id': self.suite_id,
            'name': 'Smoke Tests',
            'description': 'Critical smoke tests',
            'scope': self.suite_scope,
            'tags': ['smoke', 'critical'],
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
            'created_by': self.user_identity,
            'schedule_enabled': False,
            'total_usecases': 2
        }
        
        # Mock suite-usecase mappings
        self.mock_mappings = [
            {
                'pk': f'SUITE#{self.suite_id}',
                'sk': 'USECASE#usecase-1',
                'suite_id': self.suite_id,
                'usecase_id': 'usecase-1',
                'usecase_name': 'Test Case 1',
                'usecase_scope': 'usecase:test1',
                'added_by': self.user_identity,
                'added_at': '2024-01-01T00:00:00Z'
            },
            {
                'pk': f'SUITE#{self.suite_id}',
                'sk': 'USECASE#usecase-2',
                'suite_id': self.suite_id,
                'usecase_id': 'usecase-2',
                'usecase_name': 'Test Case 2',
                'usecase_scope': 'usecase:test2',
                'added_by': self.user_identity,
                'added_at': '2024-01-01T00:00:00Z'
            }
        ]
        
        # Base event
        self.event = {
            'pathParameters': {
                'suite_id': self.suite_id
            },
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'email': self.user_identity,
                        'sub': 'user-sub-123',
                        'scope': 'api/suite.write'
                    }
                }
            }
        }
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table', 'SCHEDULER_GROUP_NAME': 'test-group'})
    @patch('delete_test_suite.boto3.resource')
    @patch('delete_test_suite.boto3.client')
    def test_delete_suite_success(self, mock_boto_client, mock_boto_resource):
        """Test successful suite deletion without schedule"""
        # Mock DynamoDB
        mock_table = Mock()
        mock_boto_resource.return_value.Table.return_value = mock_table
        
        # Mock get_item to return suite
        mock_table.get_item.return_value = {'Item': self.mock_suite}
        
        # Mock query to return mappings
        mock_table.query.return_value = {'Items': self.mock_mappings}
        
        # Call handler
        response = delete_test_suite.handler(self.event, None)
        
        # Verify response
        self.assertEqual(response['statusCode'], 204)
        self.assertEqual(response['body'], '')
        
        # Verify get_item was called
        mock_table.get_item.assert_called_once_with(
            Key={
                'pk': 'TEST_SUITES',
                'sk': f'SUITE#{self.suite_id}'
            }
        )
        
        # Verify query was called to get mappings
        mock_table.query.assert_called_once()
        
        # Verify delete_item was called for each mapping + suite
        self.assertEqual(mock_table.delete_item.call_count, 3)  # 2 mappings + 1 suite
        
        # Verify scheduler client was not called (schedule_enabled=False)
        mock_boto_client.assert_not_called()
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table', 'SCHEDULER_GROUP_NAME': 'test-group'})
    @patch('delete_test_suite.boto3.resource')
    @patch('delete_test_suite.boto3.client')
    def test_delete_suite_with_schedule(self, mock_boto_client, mock_boto_resource):
        """Test suite deletion with enabled schedule"""
        # Enable schedule on suite
        suite_with_schedule = self.mock_suite.copy()
        suite_with_schedule['schedule_enabled'] = True
        suite_with_schedule['schedule_expression'] = 'cron(0 9 * * ? *)'
        
        # Mock DynamoDB
        mock_table = Mock()
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': suite_with_schedule}
        mock_table.query.return_value = {'Items': []}
        
        # Mock EventBridge Scheduler
        mock_scheduler = Mock()
        mock_boto_client.return_value = mock_scheduler
        
        # Call handler
        response = delete_test_suite.handler(self.event, None)
        
        # Verify response
        self.assertEqual(response['statusCode'], 204)
        
        # Verify schedule was deleted
        mock_scheduler.delete_schedule.assert_called_once_with(
            Name=self.suite_id,
            GroupName='test-group'
        )
        
        # Verify suite was deleted
        mock_table.delete_item.assert_called_once()
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table'})
    @patch('delete_test_suite.boto3.resource')
    def test_delete_suite_not_found(self, mock_boto_resource):
        """Test deleting non-existent suite"""
        # Mock DynamoDB
        mock_table = Mock()
        mock_boto_resource.return_value.Table.return_value = mock_table
        
        # Mock get_item to return no item
        mock_table.get_item.return_value = {}
        
        # Call handler
        response = delete_test_suite.handler(self.event, None)
        
        # Verify response
        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertEqual(body['error'], 'Test suite not found')
        
        # Verify delete was not called
        mock_table.delete_item.assert_not_called()
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table'})
    @patch('delete_test_suite.boto3.resource')
    def test_delete_suite_missing_suite_id(self, mock_boto_resource):
        """Test deletion with missing suite_id"""
        event = {
            'pathParameters': {},
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'email': self.user_identity,
                        'sub': 'user-sub-123',
                        'scope': 'api/suite.write'
                    }
                }
            }
        }
        
        # Call handler
        response = delete_test_suite.handler(event, None)
        
        # Verify response
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error'], 'suite_id is required')
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table'})
    @patch('delete_test_suite.boto3.resource')
    def test_delete_suite_insufficient_scope(self, mock_boto_resource):
        """Test deletion without required scope"""
        # Mock DynamoDB
        mock_table = Mock()
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': self.mock_suite}
        
        # Event with insufficient scope
        event = {
            'pathParameters': {
                'suite_id': self.suite_id
            },
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'email': self.user_identity,
                        'sub': 'user-sub-123',
                        'scope': 'api/suite.read'  # Only read, not write
                    }
                }
            }
        }
        
        # Call handler
        response = delete_test_suite.handler(event, None)
        
        # Verify response
        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Forbidden', body['error'])
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table'})
    @patch('delete_test_suite.boto3.resource')
    def test_delete_suite_no_write_access_to_scope(self, mock_boto_resource):
        """Test removed - no longer using per-suite scope validation"""
        pass
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table'})
    @patch('delete_test_suite.boto3.resource')
    def test_delete_suite_admin_scope(self, mock_boto_resource):
        """Test deletion with admin scope bypasses suite scope check"""
        # Mock DynamoDB
        mock_table = Mock()
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': self.mock_suite}
        mock_table.query.return_value = {'Items': []}
        
        # Event with admin scope
        event = {
            'pathParameters': {
                'suite_id': self.suite_id
            },
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'email': self.user_identity,
                        'sub': 'user-sub-123',
                        'scope': 'api/admin'  # Admin scope
                    }
                }
            }
        }
        
        # Call handler
        response = delete_test_suite.handler(event, None)
        
        # Verify response
        self.assertEqual(response['statusCode'], 204)
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table', 'SCHEDULER_GROUP_NAME': 'test-group'})
    @patch('delete_test_suite.boto3.resource')
    @patch('delete_test_suite.boto3.client')
    def test_delete_suite_schedule_not_found(self, mock_boto_client, mock_boto_resource):
        """Test suite deletion when schedule doesn't exist in EventBridge"""
        # Enable schedule on suite
        suite_with_schedule = self.mock_suite.copy()
        suite_with_schedule['schedule_enabled'] = True
        
        # Mock DynamoDB
        mock_table = Mock()
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': suite_with_schedule}
        mock_table.query.return_value = {'Items': []}
        
        # Mock EventBridge Scheduler to raise ResourceNotFoundException
        mock_scheduler = Mock()
        mock_scheduler.delete_schedule.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'delete_schedule'
        )
        mock_boto_client.return_value = mock_scheduler
        
        # Call handler
        response = delete_test_suite.handler(self.event, None)
        
        # Verify response - should still succeed
        self.assertEqual(response['statusCode'], 204)
        
        # Verify suite was deleted despite schedule error
        mock_table.delete_item.assert_called_once()
    
    @patch.dict('os.environ', {'TABLE_NAME': 'test-table'})
    @patch('delete_test_suite.boto3.resource')
    def test_delete_suite_no_scheduler_group_env(self, mock_boto_resource):
        """Test suite deletion when SCHEDULER_GROUP_NAME is not set"""
        # Enable schedule on suite
        suite_with_schedule = self.mock_suite.copy()
        suite_with_schedule['schedule_enabled'] = True
        
        # Mock DynamoDB
        mock_table = Mock()
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': suite_with_schedule}
        mock_table.query.return_value = {'Items': []}
        
        # Call handler (no SCHEDULER_GROUP_NAME in environment)
        response = delete_test_suite.handler(self.event, None)
        
        # Verify response - should still succeed
        self.assertEqual(response['statusCode'], 204)
        
        # Verify suite was deleted
        mock_table.delete_item.assert_called_once()


if __name__ == '__main__':
    unittest.main()
