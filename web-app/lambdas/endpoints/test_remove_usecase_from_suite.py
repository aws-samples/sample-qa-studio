"""Unit tests for remove_usecase_from_suite Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch
from remove_usecase_from_suite import handler


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
            'suite_id': 'suite-123',
            'usecase_id': 'usecase-1'
        },
        'requestContext': {
            'authorizer': {
                'email': 'test@example.com',
                'sub': 'user-123',
                'scope': 'api/suite.write api/admin'
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
def mock_mapping():
    """Create a mock suite-usecase mapping"""
    return {
        'pk': 'SUITE#suite-123',
        'sk': 'USECASE#usecase-1',
        'suite_id': 'suite-123',
        'usecase_id': 'usecase-1',
        'usecase_name': 'Test Use Case',
        'usecase_scope': 'usecase:test',
        'added_by': 'test@example.com',
        'added_at': '2024-01-01T00:00:00Z'
    }


class TestRemoveUsecaseFromSuite:
    """Test suite for remove_usecase_from_suite handler"""
    
    @patch('remove_usecase_from_suite.boto3')
    def test_remove_usecase_success(self, mock_boto3, mock_event, mock_table, mock_suite, mock_mapping):
        """Test successfully removing a use case from a suite"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite and mapping retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {'Item': mock_mapping}  # Mapping lookup
        ]
        
        # Mock delete_item
        mock_table.delete_item.return_value = {}
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 204
        assert response['body'] == ''
        
        # Verify delete_item was called
        mock_table.delete_item.assert_called_once()
        delete_call = mock_table.delete_item.call_args
        assert delete_call[1]['Key']['pk'] == 'SUITE#suite-123'
        assert delete_call[1]['Key']['sk'] == 'USECASE#usecase-1'
        
        # Verify update_item was called to decrement total_usecases
        mock_table.update_item.assert_called_once()
        update_call = mock_table.update_item.call_args
        assert update_call[1]['ExpressionAttributeValues'][':total'] == 1  # 2 - 1 = 1
    
    @patch('remove_usecase_from_suite.boto3')
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
        
        # Verify delete_item was not called
        mock_table.delete_item.assert_not_called()
    
    @patch('remove_usecase_from_suite.boto3')
    def test_mapping_not_found(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test error when mapping doesn't exist"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval (found) and mapping retrieval (not found)
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {}  # Mapping not found
        ]
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['error'] == 'Use case not found in suite'
        
        # Verify delete_item was not called
        mock_table.delete_item.assert_not_called()
    
    @patch('remove_usecase_from_suite.boto3')
    def test_missing_suite_id(self, mock_boto3):
        """Test error when suite_id is missing"""
        event = {
            'pathParameters': {
                'usecase_id': 'usecase-1'
            },
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'suite ID is required'
    
    @patch('remove_usecase_from_suite.boto3')
    def test_missing_usecase_id(self, mock_boto3):
        """Test error when usecase_id is missing"""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123'
            },
            'requestContext': {
                'authorizer': {
                    'email': 'test@example.com',
                    'sub': 'user-123',
                    'scope': 'api/suite.write'
                }
            }
        }
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'usecase ID is required'
    
    @patch('remove_usecase_from_suite.boto3')
    def test_insufficient_scope(self, mock_boto3):
        """Test error when user lacks required scope"""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'usecase_id': 'usecase-1'
            },
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
    
    @patch('remove_usecase_from_suite.boto3')
    def test_admin_scope_bypasses_validation(self, mock_boto3, mock_event, mock_table, mock_suite, mock_mapping):
        """Test that admin scope bypasses scope validation"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite and mapping retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {'Item': mock_mapping}  # Mapping lookup
        ]
        
        # Mock delete_item
        mock_table.delete_item.return_value = {}
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Execute (event already has api/admin scope)
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 204
    
    @patch('remove_usecase_from_suite.boto3')
    def test_decrement_prevents_negative_count(self, mock_boto3, mock_event, mock_table, mock_mapping):
        """Test that total_usecases doesn't go negative"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Create suite with 0 usecases (edge case)
        suite_with_zero = {
            'id': 'suite-123',
            'name': 'Test Suite',
            'scope': 'suite:test-suite',
            'total_usecases': 0
        }
        
        # Mock suite and mapping retrieval
        mock_table.get_item.side_effect = [
            {'Item': suite_with_zero},  # Suite lookup
            {'Item': mock_mapping}  # Mapping lookup
        ]
        
        # Mock delete_item
        mock_table.delete_item.return_value = {}
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 204
        
        # Verify update_item was called with 0 (not negative)
        update_call = mock_table.update_item.call_args
        assert update_call[1]['ExpressionAttributeValues'][':total'] == 0
    
    @patch('remove_usecase_from_suite.boto3')
    def test_decrement_from_one_to_zero(self, mock_boto3, mock_event, mock_table, mock_mapping):
        """Test decrementing from 1 to 0"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Create suite with 1 usecase
        suite_with_one = {
            'id': 'suite-123',
            'name': 'Test Suite',
            'scope': 'suite:test-suite',
            'total_usecases': 1
        }
        
        # Mock suite and mapping retrieval
        mock_table.get_item.side_effect = [
            {'Item': suite_with_one},  # Suite lookup
            {'Item': mock_mapping}  # Mapping lookup
        ]
        
        # Mock delete_item
        mock_table.delete_item.return_value = {}
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 204
        
        # Verify update_item was called with 0
        update_call = mock_table.update_item.call_args
        assert update_call[1]['ExpressionAttributeValues'][':total'] == 0
    
    @patch('remove_usecase_from_suite.boto3')
    def test_cors_headers_present(self, mock_boto3, mock_event, mock_table, mock_suite, mock_mapping):
        """Test that CORS headers are present in response"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite and mapping retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {'Item': mock_mapping}  # Mapping lookup
        ]
        
        # Mock delete_item and update_item
        mock_table.delete_item.return_value = {}
        mock_table.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify CORS headers
        assert 'Access-Control-Allow-Origin' in response['headers']
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
        assert 'Access-Control-Allow-Methods' in response['headers']
        assert 'Access-Control-Allow-Headers' in response['headers']
    
    @patch('remove_usecase_from_suite.boto3')
    def test_updated_at_timestamp_set(self, mock_boto3, mock_event, mock_table, mock_suite, mock_mapping):
        """Test that updated_at timestamp is set when updating suite"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite and mapping retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {'Item': mock_mapping}  # Mapping lookup
        ]
        
        # Mock delete_item and update_item
        mock_table.delete_item.return_value = {}
        mock_table.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 204
        
        # Verify update_item was called with updated_at
        update_call = mock_table.update_item.call_args
        assert ':updated_at' in update_call[1]['ExpressionAttributeValues']
        assert update_call[1]['ExpressionAttributeValues'][':updated_at']  # Not empty


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
