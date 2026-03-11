"""Unit tests for add_usecases_to_suite Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from add_usecases_to_suite import handler


@pytest.fixture
def mock_table():
    """Create a mock DynamoDB table"""
    table = Mock()
    return table


@pytest.fixture
def mock_event():
    """Create a mock API Gateway event"""
    return {
        'body': json.dumps({
            'usecase_ids': ['usecase-1', 'usecase-2']
        }),
        'pathParameters': {
            'suite_id': 'suite-123'
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
        'total_usecases': 0
    }


@pytest.fixture
def mock_usecase():
    """Create a mock use case"""
    def _create_usecase(usecase_id, name='Test Use Case', scope='usecase:test'):
        return {
            'id': usecase_id,
            'name': name,
            'scope': scope
        }
    return _create_usecase


def setup_batch_writer_mock(mock_table):
    """Helper to setup batch writer context manager mock"""
    mock_batch_writer = MagicMock()
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_batch_writer
    mock_context.__exit__.return_value = None
    mock_table.batch_writer.return_value = mock_context
    return mock_batch_writer


class TestAddUsecasesToSuite:
    """Test suite for add_usecases_to_suite handler"""
    
    @patch('add_usecases_to_suite.boto3')
    def test_add_usecases_success(self, mock_boto3, mock_event, mock_table, mock_suite, mock_usecase):
        """Test successfully adding use cases to a suite"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {'Item': mock_usecase('usecase-1', 'Use Case 1')},  # First use case
            {'Item': mock_usecase('usecase-2', 'Use Case 2')}   # Second use case
        ]
        
        # Mock existing mappings query (empty)
        mock_table.query.return_value = {'Items': []}
        
        # Mock batch writer
        mock_batch_writer = setup_batch_writer_mock(mock_table)
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['added'] == 2
        assert body['total_usecases'] == 2
        
        # Verify batch writer was called twice
        assert mock_batch_writer.put_item.call_count == 2
        
        # Verify update_item was called to update total_usecases
        mock_table.update_item.assert_called_once()
    
    @patch('add_usecases_to_suite.boto3')
    def test_add_usecases_idempotent(self, mock_boto3, mock_event, mock_table, mock_suite, mock_usecase):
        """Test that adding existing use cases is idempotent"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite}
        ]
        
        # Mock existing mappings query (both use cases already exist)
        mock_table.query.return_value = {
            'Items': [
                {'usecase_id': 'usecase-1'},
                {'usecase_id': 'usecase-2'}
            ]
        }
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['added'] == 0
        assert body['total_usecases'] == 0
        
        # Verify no batch writes or updates occurred
        mock_table.batch_writer.assert_not_called()
        mock_table.update_item.assert_not_called()
    
    @patch('add_usecases_to_suite.boto3')
    def test_add_usecases_partial_idempotent(self, mock_boto3, mock_event, mock_table, mock_suite, mock_usecase):
        """Test adding use cases when some already exist"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {'Item': mock_usecase('usecase-2', 'Use Case 2')}  # Only second use case
        ]
        
        # Mock existing mappings query (first use case already exists)
        mock_table.query.return_value = {
            'Items': [
                {'usecase_id': 'usecase-1'}
            ]
        }
        
        # Mock batch writer
        mock_batch_writer = setup_batch_writer_mock(mock_table)
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['added'] == 1
        assert body['total_usecases'] == 1
        
        # Verify batch writer was called once
        assert mock_batch_writer.put_item.call_count == 1
    
    @patch('add_usecases_to_suite.boto3')
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
    
    @patch('add_usecases_to_suite.boto3')
    def test_usecase_not_found_skipped(self, mock_boto3, mock_event, mock_table, mock_suite, mock_usecase):
        """Test that non-existent use cases are skipped"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {},  # First use case not found
            {'Item': mock_usecase('usecase-2', 'Use Case 2')}  # Second use case found
        ]
        
        # Mock existing mappings query (empty)
        mock_table.query.return_value = {'Items': []}
        
        # Mock batch writer
        mock_batch_writer = setup_batch_writer_mock(mock_table)
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['added'] == 1  # Only one use case added
        assert body['total_usecases'] == 1
    
    @patch('add_usecases_to_suite.boto3')
    def test_missing_suite_id(self, mock_boto3):
        """Test error when suite_id is missing"""
        event = {
            'body': json.dumps({'usecase_ids': ['usecase-1']}),
            'pathParameters': {},
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
    
    @patch('add_usecases_to_suite.boto3')
    def test_invalid_json_body(self, mock_boto3):
        """Test error when request body is invalid JSON"""
        event = {
            'body': 'invalid json',
            'pathParameters': {'suite_id': 'suite-123'},
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
        assert body['error'] == 'Invalid JSON in request body'
    
    @patch('add_usecases_to_suite.boto3')
    def test_empty_usecase_ids(self, mock_boto3):
        """Test error when usecase_ids is empty"""
        event = {
            'body': json.dumps({'usecase_ids': []}),
            'pathParameters': {'suite_id': 'suite-123'},
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
        assert body['error'] == 'usecase_ids cannot be empty'
    
    @patch('add_usecases_to_suite.boto3')
    def test_usecase_ids_not_array(self, mock_boto3):
        """Test error when usecase_ids is not an array"""
        event = {
            'body': json.dumps({'usecase_ids': 'not-an-array'}),
            'pathParameters': {'suite_id': 'suite-123'},
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
        assert body['error'] == 'usecase_ids must be an array'
    
    @patch('add_usecases_to_suite.boto3')
    def test_insufficient_scope(self, mock_boto3):
        """Test error when user lacks required scope"""
        event = {
            'body': json.dumps({'usecase_ids': ['usecase-1']}),
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
    
    @patch('add_usecases_to_suite.boto3')
    
    def test_suite_scope_validation(self, mock_boto3, mock_event, mock_table, mock_suite):
        """Test that suite scope is validated"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.return_value = {'Item': mock_suite}
        
        # Mock scope validation to raise PermissionError
        mock_validate.side_effect = PermissionError('User lacks write permission on suite:test-suite')
        
        # Modify event to not have admin scope
        event = mock_event.copy()
        event['requestContext']['authorizer']['scope'] = 'api/suite.write'
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'Forbidden' in body['error']
    
    @patch('add_usecases_to_suite.boto3')
    
    def test_usecase_scope_validation_skips_unauthorized(self, mock_boto3, mock_event, mock_table, mock_suite, mock_usecase):
        """Test that use cases without read access are skipped"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {'Item': mock_usecase('usecase-1', 'Use Case 1', 'usecase:restricted')},
            {'Item': mock_usecase('usecase-2', 'Use Case 2', 'usecase:allowed')}
        ]
        
        # Mock existing mappings query (empty)
        mock_table.query.return_value = {'Items': []}
        
        # Mock scope validation: first call succeeds (suite), second fails (usecase-1), third succeeds (usecase-2)
        mock_validate.side_effect = [
            None,  # Suite write access OK
            PermissionError('No read access'),  # First use case denied
            None   # Second use case OK
        ]
        
        # Mock batch writer
        mock_batch_writer = setup_batch_writer_mock(mock_table)
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Modify event to not have admin scope
        event = mock_event.copy()
        event['requestContext']['authorizer']['scope'] = 'api/suite.write'
        
        # Execute
        response = handler(event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['added'] == 1  # Only one use case added
        assert body['total_usecases'] == 1
    
    @patch('add_usecases_to_suite.boto3')
    def test_admin_scope_bypasses_validation(self, mock_boto3, mock_event, mock_table, mock_suite, mock_usecase):
        """Test that admin scope bypasses scope validation"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock suite retrieval
        mock_table.get_item.side_effect = [
            {'Item': mock_suite},  # Suite lookup
            {'Item': mock_usecase('usecase-1', 'Use Case 1')},
            {'Item': mock_usecase('usecase-2', 'Use Case 2')}
        ]
        
        # Mock existing mappings query (empty)
        mock_table.query.return_value = {'Items': []}
        
        # Mock batch writer
        mock_batch_writer = setup_batch_writer_mock(mock_table)
        
        # Mock update_item
        mock_table.update_item.return_value = {}
        
        # Execute (event already has api/admin scope)
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['added'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
