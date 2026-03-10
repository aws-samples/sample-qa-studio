"""Unit tests for list_suite_usecases Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch
from list_suite_usecases import handler


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
        'total_usecases': 2
    }


@pytest.fixture
def mock_mappings():
    """Create mock use case mappings"""
    return [
        {
            'pk': 'SUITE#suite-123',
            'sk': 'USECASE#usecase-1',
            'suite_id': 'suite-123',
            'usecase_id': 'usecase-1',
            'usecase_name': 'Login Test',
            'usecase_scope': 'usecase:login',
            'added_by': 'user@example.com',
            'added_at': '2024-01-01T10:00:00Z'
        },
        {
            'pk': 'SUITE#suite-123',
            'sk': 'USECASE#usecase-2',
            'suite_id': 'suite-123',
            'usecase_id': 'usecase-2',
            'usecase_name': 'Checkout Test',
            'usecase_scope': 'usecase:checkout',
            'added_by': 'admin@example.com',
            'added_at': '2024-01-01T11:00:00Z'
        }
    ]


class TestListSuiteUsecases:
    """Test suite for list_suite_usecases handler"""
    
    @patch('list_suite_usecases.boto3')
    def test_list_usecases_success(self, mock_boto3, mock_event, mock_table, mock_suite, mock_mappings):
        """Test successfully listing use cases in a suite"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock mappings query
        mock_table.query.return_value = {'Items': mock_mappings}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 2
        assert len(body['usecases']) == 2
        
        # Verify first use case
        usecase1 = body['usecases'][0]
        assert usecase1['usecase_id'] == 'usecase-1'
        assert usecase1['usecase_name'] == 'Login Test'
        assert usecase1['added_by'] == 'user@example.com'
        assert usecase1['added_at'] == '2024-01-01T10:00:00Z'
        
        # Verify second use case
        usecase2 = body['usecases'][1]
        assert usecase2['usecase_id'] == 'usecase-2'
        assert usecase2['usecase_name'] == 'Checkout Test'
        
        # Verify query was called correctly
        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs['ExpressionAttributeValues'][':pk'] == 'SUITE#suite-123'
        assert call_kwargs['ExpressionAttributeValues'][':sk_prefix'] == 'USECASE#'
    
    @patch('list_suite_usecases.boto3')
    def test_list_usecases_empty_suite(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test listing use cases from an empty suite"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock empty mappings query
        mock_table.query.return_value = {'Items': []}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 0
        assert body['usecases'] == []
    
    @patch('list_suite_usecases.boto3')
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
    
    @patch('list_suite_usecases.boto3')
    def test_missing_suite_id(self, mock_boto3):
        """Test error when suite_id is missing"""
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
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'suite ID is required'
    
    @patch('list_suite_usecases.boto3')
    def test_insufficient_scope(self, mock_boto3):
        """Test error when user lacks required scope"""
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
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
    
    @patch('list_suite_usecases.boto3')
    def test_admin_scope_bypasses_validation(self, mock_boto3, mock_event, mock_table, mock_suite, mock_mappings):
        """Test that admin scope bypasses scope validation"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock mappings query
        mock_table.query.return_value = {'Items': mock_mappings}
        
        # Execute (event already has api/admin scope)
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 2
    
    @patch('list_suite_usecases.boto3')
    def test_list_usecases_with_read_scope(self, mock_boto3, mock_table, mock_suite, mock_mappings):
        """Test listing use cases with read scope (no admin)"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock mappings query
        mock_table.query.return_value = {'Items': mock_mappings}
        
        # Create event without admin scope
        event = {
            'pathParameters': {'suite_id': 'suite-123'},
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
        assert body['total'] == 2
    
    @patch('list_suite_usecases.boto3')
    def test_list_usecases_metadata_fields(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test that all metadata fields are returned correctly"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock single mapping with all fields
        mapping = {
            'pk': 'SUITE#suite-123',
            'sk': 'USECASE#usecase-1',
            'suite_id': 'suite-123',
            'usecase_id': 'usecase-1',
            'usecase_name': 'Test Use Case',
            'usecase_scope': 'usecase:test',
            'added_by': 'user@example.com',
            'added_at': '2024-01-15T14:30:00Z'
        }
        mock_table.query.return_value = {'Items': [mapping]}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 1
        
        usecase = body['usecases'][0]
        assert usecase['usecase_id'] == 'usecase-1'
        assert usecase['usecase_name'] == 'Test Use Case'
        assert usecase['added_by'] == 'user@example.com'
        assert usecase['added_at'] == '2024-01-15T14:30:00Z'
    
    @patch('list_suite_usecases.boto3')
    def test_list_usecases_large_result_set(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test listing a large number of use cases"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Create 50 mock mappings
        mappings = []
        for i in range(50):
            mappings.append({
                'pk': 'SUITE#suite-123',
                'sk': f'USECASE#usecase-{i}',
                'suite_id': 'suite-123',
                'usecase_id': f'usecase-{i}',
                'usecase_name': f'Use Case {i}',
                'usecase_scope': f'usecase:test-{i}',
                'added_by': 'user@example.com',
                'added_at': '2024-01-01T10:00:00Z'
            })
        
        mock_table.query.return_value = {'Items': mappings}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['total'] == 50
        assert len(body['usecases']) == 50
    
    @patch('list_suite_usecases.boto3')
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
