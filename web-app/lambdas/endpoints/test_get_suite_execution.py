"""Unit tests for get_suite_execution Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch
from get_suite_execution import handler


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
            'execution_id': 'exec-456'
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
def mock_execution():
    """Create a mock suite execution"""
    return {
        'pk': 'SUITE_EXECUTION#suite-123',
        'sk': 'EXECUTION#exec-456',
        'id': 'exec-456',
        'suite_id': 'suite-123',
        'suite_name': 'Smoke Tests',
        'suite_scope': 'suite:smoke-tests',
        'status': 'completed',
        'started_at': '2024-01-01T10:00:00Z',
        'completed_at': '2024-01-01T10:15:00Z',
        'duration_seconds': 900,
        'triggered_by': 'user@example.com',
        'trigger_type': 'manual',
        'total_usecases': 3,
        'completed_usecases': 3,
        'successful_usecases': 2,
        'failed_usecases': 1,
        'running_usecases': 0
    }


@pytest.fixture
def mock_results():
    """Create mock execution results"""
    return [
        {
            'pk': 'USECASE_EXECUTION#usecase-1',
            'sk': 'RESULT#usecase-1',
            'suite_execution_id': 'exec-456',
            'usecase_id': 'usecase-1',
            'usecase_name': 'Login Test',
            'usecase_execution_id': 'uc-exec-1',
            'status': 'completed',
            'started_at': '2024-01-01T10:00:00Z',
            'completed_at': '2024-01-01T10:05:00Z',
            'duration_seconds': 300,
            'recording_url': 's3://bucket/recording1.mp4'
        },
        {
            'pk': 'USECASE_EXECUTION#usecase-2',
            'sk': 'RESULT#usecase-2',
            'suite_execution_id': 'exec-456',
            'usecase_id': 'usecase-2',
            'usecase_name': 'Checkout Test',
            'usecase_execution_id': 'uc-exec-2',
            'status': 'completed',
            'started_at': '2024-01-01T10:00:00Z',
            'completed_at': '2024-01-01T10:08:00Z',
            'duration_seconds': 480,
            'recording_url': 's3://bucket/recording2.mp4'
        },
        {
            'pk': 'USECASE_EXECUTION#usecase-3',
            'sk': 'RESULT#usecase-3',
            'suite_execution_id': 'exec-456',
            'usecase_id': 'usecase-3',
            'usecase_name': 'Search Test',
            'usecase_execution_id': 'uc-exec-3',
            'status': 'failed',
            'started_at': '2024-01-01T10:00:00Z',
            'completed_at': '2024-01-01T10:03:00Z',
            'duration_seconds': 180,
            'error_message': 'Element not found',
            'recording_url': 's3://bucket/recording3.mp4'
        }
    ]


class TestGetSuiteExecution:
    """Test suite for get_suite_execution handler"""
    
    @patch('get_suite_execution.boto3')
    def test_get_execution_success(self, mock_boto3, mock_event, mock_table, mock_execution, mock_results):
        """Test successfully getting suite execution with results"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock execution retrieval
        mock_table.get_item.return_value = {'Item': mock_execution}
        
        # Mock results query
        mock_table.query.return_value = {'Items': mock_results}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Verify execution metadata
        assert body['id'] == 'exec-456'
        assert body['suite_id'] == 'suite-123'
        assert body['suite_name'] == 'Smoke Tests'
        assert body['suite_scope'] == 'suite:smoke-tests'
        assert body['status'] == 'completed'
        assert body['started_at'] == '2024-01-01T10:00:00Z'
        assert body['completed_at'] == '2024-01-01T10:15:00Z'
        assert body['duration_seconds'] == 900
        assert body['triggered_by'] == 'user@example.com'
        assert body['trigger_type'] == 'manual'
        assert body['total_usecases'] == 3
        assert body['completed_usecases'] == 3
        assert body['successful_usecases'] == 2
        assert body['failed_usecases'] == 1
        assert body['running_usecases'] == 0
        
        # Verify pk/sk are not in response
        assert 'pk' not in body
        assert 'sk' not in body
        
        # Verify results array is embedded
        assert 'results' in body
        assert len(body['results']) == 3
        
        # Verify result details
        result1 = body['results'][0]
        assert result1['usecase_id'] == 'usecase-1'
        assert result1['usecase_name'] == 'Login Test'
        assert result1['status'] == 'completed'
        assert result1['duration_seconds'] == 300
        assert 'pk' not in result1
        assert 'sk' not in result1
        
        result3 = body['results'][2]
        assert result3['usecase_id'] == 'usecase-3'
        assert result3['status'] == 'failed'
        assert result3['error_message'] == 'Element not found'
        
        # Verify DynamoDB calls
        mock_table.get_item.assert_called_once_with(
            Key={
                'pk': 'SUITE_EXECUTION#suite-123',
                'sk': 'EXECUTION#exec-456'
            }
        )
    
    @patch('get_suite_execution.boto3')
    def test_get_execution_with_no_results(self, mock_boto3, mock_event, mock_table, mock_execution):
        """Test getting execution with no results (empty suite)"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock execution retrieval
        mock_table.get_item.return_value = {'Item': mock_execution}
        
        # Mock empty results query
        mock_table.query.return_value = {'Items': []}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['id'] == 'exec-456'
        assert 'results' in body
        assert body['results'] == []
    
    @patch('get_suite_execution.boto3')
    def test_get_execution_running_status(self, mock_boto3, mock_event, mock_table):
        """Test getting execution with running status"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Create running execution
        running_execution = {
            'pk': 'SUITE_EXECUTION#suite-123',
            'sk': 'EXECUTION#exec-456',
            'id': 'exec-456',
            'suite_id': 'suite-123',
            'suite_name': 'Smoke Tests',
            'suite_scope': 'suite:smoke-tests',
            'status': 'running',
            'started_at': '2024-01-01T10:00:00Z',
            'triggered_by': 'user@example.com',
            'trigger_type': 'manual',
            'total_usecases': 3,
            'completed_usecases': 1,
            'successful_usecases': 1,
            'failed_usecases': 0,
            'running_usecases': 2
        }
        
        # Create mixed results
        mixed_results = [
            {
                'pk': 'USECASE_EXECUTION#usecase-1',
                'sk': 'RESULT#usecase-1',
                'suite_execution_id': 'exec-456',
                'usecase_id': 'usecase-1',
                'usecase_name': 'Login Test',
                'status': 'completed',
                'started_at': '2024-01-01T10:00:00Z',
                'completed_at': '2024-01-01T10:05:00Z'
            },
            {
                'pk': 'USECASE_EXECUTION#usecase-1',
                'sk': 'RESULT#usecase-2',
                'suite_execution_id': 'exec-456',
                'usecase_id': 'usecase-2',
                'usecase_name': 'Checkout Test',
                'status': 'running',
                'started_at': '2024-01-01T10:00:00Z',
                'task_arn': 'arn:aws:ecs:us-east-1:123456789012:task/cluster/task-id'
            },
            {
                'pk': 'USECASE_EXECUTION#usecase-1',
                'sk': 'RESULT#usecase-3',
                'suite_execution_id': 'exec-456',
                'usecase_id': 'usecase-3',
                'usecase_name': 'Search Test',
                'status': 'pending'
            }
        ]
        
        mock_table.get_item.return_value = {'Item': running_execution}
        mock_table.query.return_value = {'Items': mixed_results}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'running'
        assert body['running_usecases'] == 2
        assert len(body['results']) == 3
        assert body['results'][1]['status'] == 'running'
        assert body['results'][2]['status'] == 'pending'
    
    @patch('get_suite_execution.boto3')
    def test_get_execution_scheduled_trigger(self, mock_boto3, mock_event, mock_table):
        """Test getting execution triggered by schedule"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Create scheduled execution
        scheduled_execution = {
            'pk': 'SUITE_EXECUTION#suite-123',
            'sk': 'EXECUTION#exec-456',
            'id': 'exec-456',
            'suite_id': 'suite-123',
            'suite_name': 'Nightly Tests',
            'suite_scope': 'suite:nightly',
            'status': 'completed',
            'started_at': '2024-01-01T02:00:00Z',
            'completed_at': '2024-01-01T02:30:00Z',
            'triggered_by': 'system',
            'trigger_type': 'scheduled',
            'total_usecases': 2,
            'completed_usecases': 2,
            'successful_usecases': 2,
            'failed_usecases': 0
        }
        
        mock_table.get_item.return_value = {'Item': scheduled_execution}
        mock_table.query.return_value = {'Items': []}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['trigger_type'] == 'scheduled'
        assert body['triggered_by'] == 'system'
    
    @patch('get_suite_execution.boto3')
    def test_missing_suite_id(self, mock_boto3):
        """Test error when suite_id is missing"""
        event = {
            'pathParameters': {
                'execution_id': 'exec-456'
            },
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
    
    @patch('get_suite_execution.boto3')
    def test_missing_execution_id(self, mock_boto3):
        """Test error when execution_id is missing"""
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
        
        response = handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'execution ID is required'
    
    @patch('get_suite_execution.boto3')
    def test_execution_not_found(self, mock_boto3, mock_event, mock_table):
        """Test error when execution doesn't exist"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock execution retrieval (not found)
        mock_table.get_item.return_value = {}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['error'] == 'Suite execution not found'
    
    @patch('get_suite_execution.boto3')
    def test_insufficient_api_scope(self, mock_boto3):
        """Test error when user lacks api/suite.read scope"""
        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456'
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
    
    @patch('get_suite_execution.boto3')
    def test_admin_scope_bypasses_validation(self, mock_boto3, mock_event, mock_table, mock_execution, mock_results):
        """Test that admin scope bypasses suite scope validation"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock execution retrieval
        mock_table.get_item.return_value = {'Item': mock_execution}
        
        # Mock results query
        mock_table.query.return_value = {'Items': mock_results}
        
        # Execute (event already has api/admin scope)
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['id'] == 'exec-456'
    
    @patch('get_suite_execution.boto3')
    def test_get_execution_with_read_scope(self, mock_boto3, mock_table, mock_execution, mock_results):
        """Test getting execution with read scope (no admin)"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock execution retrieval
        mock_table.get_item.return_value = {'Item': mock_execution}
        
        # Mock results query
        mock_table.query.return_value = {'Items': mock_results}
        
        # Create event without admin scope
        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456'
            },
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
        assert body['id'] == 'exec-456'
        assert len(body['results']) == 3
    
    @patch('get_suite_execution.boto3')
    def test_wildcard_suite_scope_grants_access(self, mock_boto3, mock_table, mock_execution, mock_results):
        """Test that suite:*:read scope grants access"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock execution retrieval
        mock_table.get_item.return_value = {'Item': mock_execution}
        
        # Mock results query
        mock_table.query.return_value = {'Items': mock_results}
        
        # Create event with wildcard scope
        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456'
            },
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
        assert body['id'] == 'exec-456'
    
    @patch('get_suite_execution.boto3')
    def test_write_permission_implies_read(self, mock_boto3, mock_table, mock_execution, mock_results):
        """Test that write permission on suite scope grants read access"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Mock execution retrieval
        mock_table.get_item.return_value = {'Item': mock_execution}
        
        # Mock results query
        mock_table.query.return_value = {'Items': mock_results}
        
        # Create event with write scope
        event = {
            'pathParameters': {
                'suite_id': 'suite-123',
                'execution_id': 'exec-456'
            },
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
        assert body['id'] == 'exec-456'
    
    @patch('get_suite_execution.boto3')
    def test_execution_with_partial_status(self, mock_boto3, mock_event, mock_table):
        """Test getting execution with partial status (some failures)"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Create partial execution
        partial_execution = {
            'pk': 'SUITE_EXECUTION#suite-123',
            'sk': 'EXECUTION#exec-456',
            'id': 'exec-456',
            'suite_id': 'suite-123',
            'suite_name': 'Smoke Tests',
            'suite_scope': 'suite:smoke-tests',
            'status': 'partial',
            'started_at': '2024-01-01T10:00:00Z',
            'completed_at': '2024-01-01T10:15:00Z',
            'triggered_by': 'user@example.com',
            'trigger_type': 'manual',
            'total_usecases': 5,
            'completed_usecases': 5,
            'successful_usecases': 3,
            'failed_usecases': 2,
            'running_usecases': 0
        }
        
        mock_table.get_item.return_value = {'Item': partial_execution}
        mock_table.query.return_value = {'Items': []}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'partial'
        assert body['successful_usecases'] == 3
        assert body['failed_usecases'] == 2
    
    @patch('get_suite_execution.boto3')
    def test_execution_with_error_message(self, mock_boto3, mock_event, mock_table):
        """Test getting execution with suite-level error message"""
        # Setup mocks
        mock_boto3.resource.return_value.Table.return_value = mock_table
        
        # Create failed execution
        failed_execution = {
            'pk': 'SUITE_EXECUTION#suite-123',
            'sk': 'EXECUTION#exec-456',
            'id': 'exec-456',
            'suite_id': 'suite-123',
            'suite_name': 'Smoke Tests',
            'suite_scope': 'suite:smoke-tests',
            'status': 'failed',
            'started_at': '2024-01-01T10:00:00Z',
            'completed_at': '2024-01-01T10:01:00Z',
            'triggered_by': 'user@example.com',
            'trigger_type': 'manual',
            'total_usecases': 3,
            'completed_usecases': 0,
            'successful_usecases': 0,
            'failed_usecases': 0,
            'running_usecases': 0,
            'error_message': 'Failed to spawn ECS tasks'
        }
        
        mock_table.get_item.return_value = {'Item': failed_execution}
        mock_table.query.return_value = {'Items': []}
        
        # Execute
        response = handler(mock_event, None)
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'failed'
        assert body['error_message'] == 'Failed to spawn ECS tasks'
    
    @patch('get_suite_execution.boto3')
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

    @patch('get_suite_execution.boto3')
    def test_suite_execution_record_filtered_from_results(self, mock_boto3, mock_event, mock_table, mock_execution):
        """Test that only actual use case execution records appear in results.
        
        The suite execution record no longer has suite_execution_id as an attribute,
        so it won't appear in the GSI. This test verifies the handler correctly
        processes only USECASE_EXECUTION# and SUITE_EXEC# records from the GSI.
        """
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {'Item': mock_execution}

        # GSI returns only the real use case execution (suite execution record
        # no longer has suite_execution_id attribute, so it's not in the GSI)
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'USECASE_EXECUTION#usecase-1',
                    'sk': 'EXECUTION#uc-exec-1',
                    'suite_execution_id': 'exec-456',
                    'usecase_name': 'Login Test',
                    'status': 'pending',
                    'created_at': '2024-01-01T10:00:00Z',
                },
            ]
        }

        response = handler(mock_event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['results']) == 1
        assert body['results'][0]['usecase_id'] == 'usecase-1'
        assert body['results'][0]['usecase_name'] == 'Login Test'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
