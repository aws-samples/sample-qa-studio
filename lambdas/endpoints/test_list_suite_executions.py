"""Unit tests for list_suite_executions Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch
from list_suite_executions import handler


@pytest.fixture
def mock_table():
    """Create a mock DynamoDB table"""
    table = Mock()
    return table


@pytest.fixture
def mock_event():
    """Create a mock API Gateway event"""
    return {
        'pathParameters': {
            'suite_id': 'suite-123'
        },
        'queryStringParameters': None,
        'requestContext': {
            'authorizer': {
                'email': 'test@example.com',
                'sub': 'user-123',
                'scope': 'api/suite.read api/admin'
            }
        }
    }


@pytest.fixture
def mock_suite():
    """Create a mock test suite"""
    return {
        'id': 'suite-123',
        'name': 'Test Suite',
        'scope': 'suite:test-suite',
        'total_usecases': 5
    }


@pytest.fixture
def mock_executions():
    """Create mock suite executions"""
    return [
        {
            'pk': 'SUITE_EXECUTION#suite-123',
            'sk': 'EXECUTION#exec-3',
            'id': 'exec-3',
            'suite_id': 'suite-123',
            'suite_name': 'Test Suite',
            'suite_scope': 'suite:test-suite',
            'status': 'completed',
            'started_at': '2024-01-03T10:00:00Z',
            'completed_at': '2024-01-03T10:15:00Z',
            'triggered_by': 'user@example.com',
            'trigger_type': 'manual',
            'total_usecases': 5,
            'completed_usecases': 5,
            'successful_usecases': 5,
            'failed_usecases': 0,
            'running_usecases': 0
        },
        {
            'pk': 'SUITE_EXECUTION#suite-123',
            'sk': 'EXECUTION#exec-2',
            'id': 'exec-2',
            'suite_id': 'suite-123',
            'suite_name': 'Test Suite',
            'suite_scope': 'suite:test-suite',
            'status': 'partial',
            'started_at': '2024-01-02T10:00:00Z',
            'completed_at': '2024-01-02T10:20:00Z',
            'triggered_by': 'admin@example.com',
            'trigger_type': 'scheduled',
            'total_usecases': 5,
            'completed_usecases': 5,
            'successful_usecases': 3,
            'failed_usecases': 2,
            'running_usecases': 0
        },
        {
            'pk': 'SUITE_EXECUTION#suite-123',
            'sk': 'EXECUTION#exec-1',
            'id': 'exec-1',
            'suite_id': 'suite-123',
            'suite_name': 'Test Suite',
            'suite_scope': 'suite:test-suite',
            'status': 'running',
            'started_at': '2024-01-01T10:00:00Z',
            'triggered_by': 'user@example.com',
            'trigger_type': 'manual',
            'total_usecases': 5,
            'completed_usecases': 2,
            'successful_usecases': 2,
            'failed_usecases': 0,
            'running_usecases': 3
        }
    ]


class TestListSuiteExecutions:
    """Test suite for list_suite_executions handler"""
    
    @patch('list_suite_executions.boto3')
    def test_list_executions_success(self, mock_boto3, mock_event, mock_table, mock_suite, mock_executions):
        """Test successfully listing suite executions"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock executions query
        mock_table.query.return_value = {'Items': mock_executions}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 3
        assert len(body['executions']) == 3
        assert body['has_more'] is False
        
        # Verify executions are sorted by started_at descending (most recent first)
        assert body['executions'][0]['id'] == 'exec-3'
        assert body['executions'][1]['id'] == 'exec-2'
        assert body['executions'][2]['id'] == 'exec-1'
        
        # Verify pk/sk are removed from response
        assert 'pk' not in body['executions'][0]
        assert 'sk' not in body['executions'][0]
        
        # Verify execution metadata
        exec1 = body['executions'][0]
        assert exec1['status'] == 'completed'
        assert exec1['started_at'] == '2024-01-03T10:00:00Z'
        assert exec1['completed_at'] == '2024-01-03T10:15:00Z'
        assert exec1['triggered_by'] == 'user@example.com'
        assert exec1['trigger_type'] == 'manual'
        assert exec1['total_usecases'] == 5
        assert exec1['successful_usecases'] == 5
        assert exec1['failed_usecases'] == 0
    
    @patch('list_suite_executions.boto3')
    def test_list_executions_with_limit(self, mock_boto3, mock_event, mock_table, mock_suite, mock_executions):
        """Test listing executions with pagination limit"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock executions query
        mock_table.query.return_value = {'Items': mock_executions}
        
        # Add limit parameter
        event = mock_event.copy()
        event['queryStringParameters'] = {'limit': '2'}
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 2
        assert len(body['executions']) == 2
        assert body['has_more'] is True
        
        # Verify only first 2 executions returned
        assert body['executions'][0]['id'] == 'exec-3'
        assert body['executions'][1]['id'] == 'exec-2'
    
    @patch('list_suite_executions.boto3')
    def test_list_executions_with_status_filter(self, mock_boto3, mock_event, mock_table, mock_suite, mock_executions):
        """Test listing executions with status filter"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock executions query
        mock_table.query.return_value = {'Items': mock_executions}
        
        # Add status filter
        event = mock_event.copy()
        event['queryStringParameters'] = {'status': 'completed'}
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 1
        assert len(body['executions']) == 1
        assert body['executions'][0]['status'] == 'completed'
        assert body['executions'][0]['id'] == 'exec-3'
    
    @patch('list_suite_executions.boto3')
    def test_list_executions_with_status_and_limit(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test listing executions with both status filter and limit"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Create multiple completed executions
        completed_executions = [
            {
                'pk': 'SUITE_EXECUTION#suite-123',
                'sk': f'EXECUTION#exec-{i}',
                'id': f'exec-{i}',
                'suite_id': 'suite-123',
                'status': 'completed',
                'started_at': f'2024-01-{10-i:02d}T10:00:00Z',
                'triggered_by': 'user@example.com',
                'trigger_type': 'manual',
                'total_usecases': 5,
                'completed_usecases': 5,
                'successful_usecases': 5,
                'failed_usecases': 0
            }
            for i in range(5)
        ]
        
        mock_table.query.return_value = {'Items': completed_executions}
        
        # Add status filter and limit
        event = mock_event.copy()
        event['queryStringParameters'] = {'status': 'completed', 'limit': '3'}
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 3
        assert len(body['executions']) == 3
        assert body['has_more'] is True
        assert all(e['status'] == 'completed' for e in body['executions'])
    
    @patch('list_suite_executions.boto3')
    def test_list_executions_empty_result(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test listing executions when suite has no executions"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock empty executions query
        mock_table.query.return_value = {'Items': []}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 0
        assert body['executions'] == []
        assert body['has_more'] is False
    
    @patch('list_suite_executions.boto3')
    def test_suite_not_found(self, mock_boto3, mock_event, mock_table):
        """Test error when suite doesn't exist"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval (not found)
        mock_table.get_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['error'] == 'Test suite not found'
    
    @patch('list_suite_executions.boto3')
    def test_missing_suite_id(self, mock_boto3):
        """Test error when suite_id is missing"""
        event = {
            'pathParameters': {},
            'queryStringParameters': None,
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.read'
                }
            }
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Missing suite ID'
    
    @patch('list_suite_executions.boto3')
    def test_insufficient_scope(self, mock_boto3):
        """Test error when user lacks required scope"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'queryStringParameters': None,
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/usecases.read'  # Wrong scope
                }
            }
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'Forbidden' in body['error']
    
    @patch('list_suite_executions.boto3')
    @patch('list_suite_executions.validate_scope_access')
    def test_suite_scope_validation(self, mock_validate, mock_boto3, mock_event, mock_table, mock_suite):
        """Test that suite scope is validated"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock scope validation to raise PermissionError
        mock_validate.side_effect = PermissionError('User lacks read permission on suite:test-suite')
        
        # Modify event to not have admin scope
        event = mock_event.copy()
        event['requestContext']['authorizer']['scope'] = 'api/suite.read'
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'Forbidden' in body['error']
        assert 'User lacks read permission' in body['message']
    
    @patch('list_suite_executions.boto3')
    def test_admin_scope_bypasses_validation(self, mock_boto3, mock_event, mock_table, mock_suite, mock_executions):
        """Test that admin scope bypasses scope validation"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock executions query
        mock_table.query.return_value = {'Items': mock_executions}
        
        # Execute (event already has api/admin scope)
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 3
    
    @patch('list_suite_executions.boto3')
    def test_list_executions_with_read_scope(self, mock_boto3, mock_table, mock_suite, mock_executions):
        """Test listing executions with read scope (no admin)"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock executions query
        mock_table.query.return_value = {'Items': mock_executions}
        
        # Create event without admin scope
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
            'queryStringParameters': None,
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.read'
                }
            }
        }
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 3
    
    @patch('list_suite_executions.boto3')
    def test_invalid_limit_too_small(self, mock_boto3, mock_event):
        """Test error when limit is less than 1"""
        event = mock_event.copy()
        event['queryStringParameters'] = {'limit': '0'}
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Limit must be between 1 and 100' in body['error']
    
    @patch('list_suite_executions.boto3')
    def test_invalid_limit_too_large(self, mock_boto3, mock_event):
        """Test error when limit is greater than 100"""
        event = mock_event.copy()
        event['queryStringParameters'] = {'limit': '101'}
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Limit must be between 1 and 100' in body['error']
    
    @patch('list_suite_executions.boto3')
    def test_invalid_status_filter(self, mock_boto3, mock_event):
        """Test error when status filter is invalid"""
        event = mock_event.copy()
        event['queryStringParameters'] = {'status': 'invalid_status'}
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid status' in body['error']
    
    @patch('list_suite_executions.boto3')
    def test_default_limit(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test that default limit is 10"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Create 15 executions
        executions = [
            {
                'pk': 'SUITE_EXECUTION#suite-123',
                'sk': f'EXECUTION#exec-{i}',
                'id': f'exec-{i}',
                'suite_id': 'suite-123',
                'status': 'completed',
                'started_at': f'2024-01-{15-i:02d}T10:00:00Z',
                'triggered_by': 'user@example.com',
                'trigger_type': 'manual',
                'total_usecases': 5
            }
            for i in range(15)
        ]
        
        mock_table.query.return_value = {'Items': executions}
        
        # Execute without limit parameter
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 10  # Default limit
        assert len(body['executions']) == 10
        assert body['has_more'] is True
    
    @patch('list_suite_executions.boto3')
    def test_execution_sorting_by_started_at(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test that executions are sorted by started_at descending"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Create executions with different timestamps (not in order)
        executions = [
            {
                'pk': 'SUITE_EXECUTION#suite-123',
                'sk': 'EXECUTION#exec-2',
                'id': 'exec-2',
                'suite_id': 'suite-123',
                'status': 'completed',
                'started_at': '2024-01-05T10:00:00Z',
                'trigger_type': 'manual',
                'total_usecases': 5
            },
            {
                'pk': 'SUITE_EXECUTION#suite-123',
                'sk': 'EXECUTION#exec-1',
                'id': 'exec-1',
                'suite_id': 'suite-123',
                'status': 'completed',
                'started_at': '2024-01-10T10:00:00Z',
                'trigger_type': 'manual',
                'total_usecases': 5
            },
            {
                'pk': 'SUITE_EXECUTION#suite-123',
                'sk': 'EXECUTION#exec-3',
                'id': 'exec-3',
                'suite_id': 'suite-123',
                'status': 'completed',
                'started_at': '2024-01-01T10:00:00Z',
                'trigger_type': 'manual',
                'total_usecases': 5
            }
        ]
        
        mock_table.query.return_value = {'Items': executions}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 3
        
        # Verify sorting (most recent first)
        assert body['executions'][0]['started_at'] == '2024-01-10T10:00:00Z'
        assert body['executions'][1]['started_at'] == '2024-01-05T10:00:00Z'
        assert body['executions'][2]['started_at'] == '2024-01-01T10:00:00Z'
    
    @patch('list_suite_executions.boto3')
    def test_internal_error_handling(self, mock_boto3, mock_event, mock_table):
        """Test error handling for internal errors"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock get_item to raise an exception
        mock_table.get_item.side_effect = Exception('Database error')
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error'] == 'Internal server error'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
