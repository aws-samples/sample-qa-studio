"""
Unit tests for Cache Builder Lambda (build_cache.py)

Tests the event-driven Lambda function that builds step caches from Nova Act
responses after successful test executions.
"""

import json
import os
from unittest.mock import MagicMock, patch, Mock

import pytest
from botocore.exceptions import ClientError

# Import the Lambda handler and functions
import build_cache


@pytest.fixture
def mock_env_vars():
    """Mock environment variables."""
    with patch.dict(os.environ, {
        'DYNAMODB_TABLE_NAME': 'test-table',
        'S3_BUCKET': 'test-bucket'
    }):
        yield


@pytest.fixture
def valid_event():
    """Valid EventBridge event."""
    return {
        'source': 'qa-studio.worker',
        'detail-type': 'usecase.execution.completed',
        'detail': {
            'usecase_id': 'uc_123',
            'execution_id': 'exec_456',
            'execution_status': 'success',
            'timestamp': '2024-01-01T12:00:00.000Z'
        }
    }


@pytest.fixture
def mock_dynamodb_table():
    """Mock DynamoDB table resource."""
    table = MagicMock()
    return table


class TestCheckCacheEligibility:
    """Tests for check_cache_eligibility function."""
    
    def test_cache_enabled_returns_true(self, mock_dynamodb_table):
        """Test that function returns True when enable_cache is True."""
        mock_dynamodb_table.get_item.return_value = {
            'Item': {
                'pk': 'USECASES',
                'sk': 'USECASE#uc_123',
                'enable_cache': True
            }
        }
        
        result = build_cache.check_cache_eligibility(mock_dynamodb_table, 'uc_123')
        
        assert result is True
        mock_dynamodb_table.get_item.assert_called_once_with(
            Key={'pk': 'USECASES', 'sk': 'USECASE#uc_123'}
        )
    
    def test_cache_disabled_returns_false(self, mock_dynamodb_table):
        """Test that function returns False when enable_cache is False."""
        mock_dynamodb_table.get_item.return_value = {
            'Item': {
                'pk': 'USECASES',
                'sk': 'USECASE#uc_123',
                'enable_cache': False
            }
        }
        
        result = build_cache.check_cache_eligibility(mock_dynamodb_table, 'uc_123')
        
        assert result is False
    
    def test_missing_enable_cache_field_returns_false(self, mock_dynamodb_table):
        """Test that function returns False when enable_cache field is missing."""
        mock_dynamodb_table.get_item.return_value = {
            'Item': {
                'pk': 'USECASES',
                'sk': 'USECASE#uc_123'
            }
        }
        
        result = build_cache.check_cache_eligibility(mock_dynamodb_table, 'uc_123')
        
        assert result is False
    
    def test_missing_usecase_record_returns_false(self, mock_dynamodb_table):
        """Test that function returns False when USECASE record doesn't exist."""
        mock_dynamodb_table.get_item.return_value = {}
        
        result = build_cache.check_cache_eligibility(mock_dynamodb_table, 'uc_123')
        
        assert result is False
    
    def test_dynamodb_client_error_returns_false(self, mock_dynamodb_table):
        """Test that function returns False on DynamoDB ClientError."""
        mock_dynamodb_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Table not found'}},
            'GetItem'
        )
        
        result = build_cache.check_cache_eligibility(mock_dynamodb_table, 'uc_123')
        
        assert result is False
    
    def test_unexpected_error_returns_false(self, mock_dynamodb_table):
        """Test that function returns False on unexpected exceptions."""
        mock_dynamodb_table.get_item.side_effect = Exception('Unexpected error')
        
        result = build_cache.check_cache_eligibility(mock_dynamodb_table, 'uc_123')
        
        assert result is False


class TestDiscoverActFiles:
    """Tests for discover_act_files function."""
    
    def test_successful_act_file_discovery(self):
        """Test successful discovery and mapping of act files."""
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'uc_123/exec_456/session_abc/act_act_789.json'},
                {'Key': 'uc_123/exec_456/session_abc/act_act_790.json'},
                {'Key': 'uc_123/exec_456/session_abc/act_act_791.json'}
            ]
        }
        
        result = build_cache.discover_act_files(mock_s3_client, 'test-bucket', 'uc_123', 'exec_456', 'session_abc')
        
        assert len(result) == 3
        assert result['act_789'] == 'uc_123/exec_456/session_abc/act_act_789.json'
        assert result['act_790'] == 'uc_123/exec_456/session_abc/act_act_790.json'
        assert result['act_791'] == 'uc_123/exec_456/session_abc/act_act_791.json'
        mock_s3_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket',
            Prefix='uc_123/exec_456/session_abc/act_'
        )
    
    def test_empty_s3_results_returns_empty_dict(self):
        """Test that function returns empty dict when no act files found."""
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {}  # No Contents key
        
        result = build_cache.discover_act_files(mock_s3_client, 'test-bucket', 'uc_123', 'exec_456', 'session_abc')
        
        assert result == {}
    
    def test_act_id_extraction_with_various_formats(self):
        """Test act_id extraction from various S3 key formats."""
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'uc_123/exec_456/session_abc/act_simple_id.json'},
                {'Key': 'uc_123/exec_456/session_abc/act_id-with-dashes.json'},
                {'Key': 'uc_123/exec_456/session_abc/act_id_with_underscores.json'},
                {'Key': 'uc_123/exec_456/session_abc/act_123456.json'}
            ]
        }
        
        result = build_cache.discover_act_files(mock_s3_client, 'test-bucket', 'uc_123', 'exec_456', 'session_abc')
        
        assert len(result) == 4
        assert 'simple_id' in result
        assert 'id-with-dashes' in result
        assert 'id_with_underscores' in result
        assert '123456' in result
    
    def test_invalid_key_format_skipped(self):
        """Test that keys not matching pattern are skipped with warning."""
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'uc_123/exec_456/session_abc/act_valid_id.json'},
                {'Key': 'uc_123/exec_456/recording/video.webm'},
                {'Key': 'uc_123/exec_456/session_abc/other_file.txt'}
            ]
        }
        
        result = build_cache.discover_act_files(mock_s3_client, 'test-bucket', 'uc_123', 'exec_456', 'session_abc')
        
        # Only the valid key should be in the result
        assert len(result) == 1
        assert 'valid_id' in result
    
    def test_s3_client_error_returns_empty_dict(self):
        """Test that S3 ClientError is handled gracefully."""
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            'ListObjectsV2'
        )
        
        result = build_cache.discover_act_files(mock_s3_client, 'test-bucket', 'uc_123', 'exec_456', 'session_abc')
        
        assert result == {}
    
    def test_unexpected_error_returns_empty_dict(self):
        """Test that unexpected exceptions are handled gracefully."""
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.side_effect = Exception('Unexpected error')
        
        result = build_cache.discover_act_files(mock_s3_client, 'test-bucket', 'uc_123', 'exec_456', 'session_abc')
        
        assert result == {}
    
    def test_correct_prefix_construction(self):
        """Test that S3 prefix is constructed correctly."""
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {}
        
        build_cache.discover_act_files(mock_s3_client, 'test-bucket', 'my_uc_123', 'my_exec_123', 'my_session_456')
        
        mock_s3_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket',
            Prefix='my_uc_123/my_exec_123/my_session_456/act_'
        )


class TestGetNovaSessionId:
    """Tests for get_nova_session_id function."""

    def test_returns_session_id_when_present(self, mock_dynamodb_table):
        """Test successful retrieval of nova_session_id."""
        mock_dynamodb_table.get_item.return_value = {
            'Item': {
                'pk': 'USECASE#uc_123',
                'sk': 'EXECUTION#exec_456',
                'nova_session_id': 'session_abc'
            }
        }

        result = build_cache.get_nova_session_id(mock_dynamodb_table, 'uc_123', 'exec_456')

        assert result == 'session_abc'
        mock_dynamodb_table.get_item.assert_called_once_with(
            Key={'pk': 'USECASE#uc_123', 'sk': 'EXECUTION#exec_456'}
        )

    def test_returns_none_when_record_missing(self, mock_dynamodb_table):
        """Test returns None when execution record doesn't exist."""
        mock_dynamodb_table.get_item.return_value = {}

        result = build_cache.get_nova_session_id(mock_dynamodb_table, 'uc_123', 'exec_456')

        assert result is None

    def test_returns_none_when_field_missing(self, mock_dynamodb_table):
        """Test returns None when nova_session_id field is not set."""
        mock_dynamodb_table.get_item.return_value = {
            'Item': {
                'pk': 'USECASE#uc_123',
                'sk': 'EXECUTION#exec_456'
            }
        }

        result = build_cache.get_nova_session_id(mock_dynamodb_table, 'uc_123', 'exec_456')

        assert result is None

    def test_returns_none_on_client_error(self, mock_dynamodb_table):
        """Test returns None on DynamoDB ClientError."""
        mock_dynamodb_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'error'}},
            'GetItem'
        )

        result = build_cache.get_nova_session_id(mock_dynamodb_table, 'uc_123', 'exec_456')

        assert result is None

    def test_returns_none_on_unexpected_error(self, mock_dynamodb_table):
        """Test returns None on unexpected exception."""
        mock_dynamodb_table.get_item.side_effect = Exception('Unexpected')

        result = build_cache.get_nova_session_id(mock_dynamodb_table, 'uc_123', 'exec_456')

        assert result is None


class TestGetExecutionSteps:
    """Tests for get_execution_steps function."""
    
    def test_successful_query_returns_steps(self, mock_dynamodb_table):
        """Test successful query returns list of EXECUTION_STEP records."""
        mock_dynamodb_table.query.return_value = {
            'Items': [
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_1',
                    'step_id': 'step_1',
                    'step_type': 'navigation',
                    'act_id': 'act_789'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_2',
                    'step_id': 'step_2',
                    'step_type': 'assertion',
                    'act_id': None
                }
            ]
        }
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert len(result) == 2
        assert result[0]['step_id'] == 'step_1'
        assert result[1]['step_id'] == 'step_2'
        
        # Verify query was called with correct parameters
        call_args = mock_dynamodb_table.query.call_args
        assert call_args is not None
    
    def test_empty_results_returns_empty_list(self, mock_dynamodb_table):
        """Test that function returns empty list when no steps found."""
        mock_dynamodb_table.query.return_value = {'Items': []}
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert result == []
    
    def test_missing_items_key_returns_empty_list(self, mock_dynamodb_table):
        """Test that function returns empty list when Items key is missing."""
        mock_dynamodb_table.query.return_value = {}
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert result == []
    
    def test_dynamodb_client_error_returns_empty_list(self, mock_dynamodb_table):
        """Test that DynamoDB ClientError is handled gracefully."""
        mock_dynamodb_table.query.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Table not found'}},
            'Query'
        )
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert result == []
    
    def test_unexpected_error_returns_empty_list(self, mock_dynamodb_table):
        """Test that unexpected exceptions are handled gracefully."""
        mock_dynamodb_table.query.side_effect = Exception('Unexpected error')
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert result == []
    
    def test_query_with_correct_key_condition(self, mock_dynamodb_table):
        """Test that query uses correct KeyConditionExpression."""
        mock_dynamodb_table.query.return_value = {'Items': []}
        
        build_cache.get_execution_steps(mock_dynamodb_table, 'my_exec_123')
        
        # Verify query was called once
        assert mock_dynamodb_table.query.call_count == 1
        
        # Verify KeyConditionExpression parameter was passed
        call_kwargs = mock_dynamodb_table.query.call_args[1]
        assert 'KeyConditionExpression' in call_kwargs


class TestGetExecutionSteps:
    """Tests for get_execution_steps function."""
    
    def test_successful_query_returns_steps(self, mock_dynamodb_table):
        """Test successful query returns list of EXECUTION_STEP records."""
        mock_dynamodb_table.query.return_value = {
            'Items': [
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_1',
                    'step_id': 'step_1',
                    'step_type': 'navigation',
                    'act_id': 'act_789'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_2',
                    'step_id': 'step_2',
                    'step_type': 'assertion',
                    'act_id': None
                }
            ]
        }
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert len(result) == 2
        assert result[0]['step_id'] == 'step_1'
        assert result[1]['step_id'] == 'step_2'
        
        # Verify query was called with correct parameters
        call_args = mock_dynamodb_table.query.call_args
        assert call_args is not None
    
    def test_empty_results_returns_empty_list(self, mock_dynamodb_table):
        """Test that function returns empty list when no steps found."""
        mock_dynamodb_table.query.return_value = {'Items': []}
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert result == []
    
    def test_missing_items_key_returns_empty_list(self, mock_dynamodb_table):
        """Test that function returns empty list when Items key is missing."""
        mock_dynamodb_table.query.return_value = {}
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert result == []
    
    def test_dynamodb_client_error_returns_empty_list(self, mock_dynamodb_table):
        """Test that DynamoDB ClientError is handled gracefully."""
        mock_dynamodb_table.query.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Table not found'}},
            'Query'
        )
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert result == []
    
    def test_unexpected_error_returns_empty_list(self, mock_dynamodb_table):
        """Test that unexpected exceptions are handled gracefully."""
        mock_dynamodb_table.query.side_effect = Exception('Unexpected error')
        
        result = build_cache.get_execution_steps(mock_dynamodb_table, 'exec_456')
        
        assert result == []
    
    def test_query_with_correct_key_condition(self, mock_dynamodb_table):
        """Test that query uses correct KeyConditionExpression."""
        mock_dynamodb_table.query.return_value = {'Items': []}
        
        build_cache.get_execution_steps(mock_dynamodb_table, 'my_exec_123')
        
        # Verify query was called once
        assert mock_dynamodb_table.query.call_count == 1
        
        # Verify KeyConditionExpression parameter was passed
        call_kwargs = mock_dynamodb_table.query.call_args[1]
        assert 'KeyConditionExpression' in call_kwargs


class TestFilterNavigationSteps:
    """Tests for filter_navigation_steps function."""
    
    def test_filters_only_navigation_steps(self):
        """Test that function filters to only navigation steps."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'assertion',
                'act_id': 'act_790'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_3',
                'step_id': 'step_3',
                'step_type': 'navigation',
                'act_id': 'act_791'
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json',
            'act_790': 'executions/exec_456/act_act_790.json',
            'act_791': 'executions/exec_456/act_act_791.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 2
        assert all(step['step_type'] == 'navigation' for step in result)
        assert result[0]['step_id'] == 'step_1'
        assert result[1]['step_id'] == 'step_3'
    
    def test_skips_steps_with_missing_act_id(self):
        """Test that function skips steps where act_id is missing."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation'
                # Missing act_id field
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 1
        assert result[0]['step_id'] == 'step_1'
    
    def test_skips_steps_with_null_act_id(self):
        """Test that function skips steps where act_id is None."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation',
                'act_id': None
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 1
        assert result[0]['step_id'] == 'step_1'
    
    def test_skips_steps_with_act_id_not_in_mapping(self):
        """Test that function skips steps where act_id is not in act_mapping."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation',
                'act_id': 'act_999'  # Not in mapping
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 1
        assert result[0]['step_id'] == 'step_1'
    
    def test_empty_steps_returns_empty_list(self):
        """Test that function returns empty list when steps is empty."""
        steps = []
        act_mapping = {'act_789': 'executions/exec_456/act_act_789.json'}
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert result == []
    
    def test_empty_act_mapping_returns_empty_list(self):
        """Test that function returns empty list when act_mapping is empty."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            }
        ]
        act_mapping = {}
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert result == []
    
    def test_no_navigation_steps_returns_empty_list(self):
        """Test that function returns empty list when no navigation steps exist."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'assertion',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'validation',
                'act_id': 'act_790'
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json',
            'act_790': 'executions/exec_456/act_act_790.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert result == []
    
    def test_all_navigation_steps_with_valid_act_ids(self):
        """Test that function returns all steps when all are valid navigation steps."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation',
                'act_id': 'act_790'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_3',
                'step_id': 'step_3',
                'step_type': 'navigation',
                'act_id': 'act_791'
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json',
            'act_790': 'executions/exec_456/act_act_790.json',
            'act_791': 'executions/exec_456/act_act_791.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 3
        assert result[0]['step_id'] == 'step_1'
        assert result[1]['step_id'] == 'step_2'
        assert result[2]['step_id'] == 'step_3'
    
    def test_mixed_scenarios(self):
        """Test function with mixed scenarios: valid, missing act_id, null act_id, unmatched act_id, non-navigation."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'  # Valid
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation'
                # Missing act_id
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_3',
                'step_id': 'step_3',
                'step_type': 'navigation',
                'act_id': None  # Null act_id
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_4',
                'step_id': 'step_4',
                'step_type': 'navigation',
                'act_id': 'act_999'  # Not in mapping
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_5',
                'step_id': 'step_5',
                'step_type': 'assertion',
                'act_id': 'act_790'  # Not navigation
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_6',
                'step_id': 'step_6',
                'step_type': 'navigation',
                'act_id': 'act_790'  # Valid
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json',
            'act_790': 'executions/exec_456/act_act_790.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 2
        assert result[0]['step_id'] == 'step_1'
        assert result[1]['step_id'] == 'step_6'


class TestFilterNavigationSteps:
    """Tests for filter_navigation_steps function."""
    
    def test_filters_only_navigation_steps(self):
        """Test that function filters to only navigation steps."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'assertion',
                'act_id': 'act_790'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_3',
                'step_id': 'step_3',
                'step_type': 'navigation',
                'act_id': 'act_791'
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json',
            'act_790': 'executions/exec_456/act_act_790.json',
            'act_791': 'executions/exec_456/act_act_791.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 2
        assert all(step['step_type'] == 'navigation' for step in result)
        assert result[0]['step_id'] == 'step_1'
        assert result[1]['step_id'] == 'step_3'
    
    def test_skips_steps_with_missing_act_id(self):
        """Test that function skips steps where act_id is missing."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation'
                # Missing act_id field
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 1
        assert result[0]['step_id'] == 'step_1'
    
    def test_skips_steps_with_null_act_id(self):
        """Test that function skips steps where act_id is None."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation',
                'act_id': None
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 1
        assert result[0]['step_id'] == 'step_1'
    
    def test_skips_steps_with_act_id_not_in_mapping(self):
        """Test that function skips steps where act_id is not in act_mapping."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation',
                'act_id': 'act_999'  # Not in mapping
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 1
        assert result[0]['step_id'] == 'step_1'
    
    def test_empty_steps_returns_empty_list(self):
        """Test that function returns empty list when steps is empty."""
        steps = []
        act_mapping = {'act_789': 'executions/exec_456/act_act_789.json'}
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert result == []
    
    def test_empty_act_mapping_returns_empty_list(self):
        """Test that function returns empty list when act_mapping is empty."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            }
        ]
        act_mapping = {}
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert result == []
    
    def test_no_navigation_steps_returns_empty_list(self):
        """Test that function returns empty list when no navigation steps exist."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'assertion',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'validation',
                'act_id': 'act_790'
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json',
            'act_790': 'executions/exec_456/act_act_790.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert result == []
    
    def test_all_navigation_steps_with_valid_act_ids(self):
        """Test that function returns all steps when all are valid navigation steps."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation',
                'act_id': 'act_790'
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_3',
                'step_id': 'step_3',
                'step_type': 'navigation',
                'act_id': 'act_791'
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json',
            'act_790': 'executions/exec_456/act_act_790.json',
            'act_791': 'executions/exec_456/act_act_791.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 3
        assert result[0]['step_id'] == 'step_1'
        assert result[1]['step_id'] == 'step_2'
        assert result[2]['step_id'] == 'step_3'
    
    def test_mixed_scenarios(self):
        """Test function with mixed scenarios: valid, missing act_id, null act_id, unmatched act_id, non-navigation."""
        steps = [
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_1',
                'step_id': 'step_1',
                'step_type': 'navigation',
                'act_id': 'act_789'  # Valid
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_2',
                'step_id': 'step_2',
                'step_type': 'navigation'
                # Missing act_id
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_3',
                'step_id': 'step_3',
                'step_type': 'navigation',
                'act_id': None  # Null act_id
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_4',
                'step_id': 'step_4',
                'step_type': 'navigation',
                'act_id': 'act_999'  # Not in mapping
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_5',
                'step_id': 'step_5',
                'step_type': 'assertion',
                'act_id': 'act_790'  # Not navigation
            },
            {
                'pk': 'EXECUTION#exec_456',
                'sk': 'EXECUTION_STEP#exec_step_6',
                'step_id': 'step_6',
                'step_type': 'navigation',
                'act_id': 'act_790'  # Valid
            }
        ]
        act_mapping = {
            'act_789': 'executions/exec_456/act_act_789.json',
            'act_790': 'executions/exec_456/act_act_790.json'
        }
        
        result = build_cache.filter_navigation_steps(steps, act_mapping)
        
        assert len(result) == 2
        assert result[0]['step_id'] == 'step_1'
        assert result[1]['step_id'] == 'step_6'


class TestFetchAndParseActResponse:
    """Tests for fetch_and_parse_act_response function."""
    
    @patch('build_cache.parse_nova_act_steps')
    def test_successful_fetch_and_parse(self, mock_parse):
        """Test successful S3 fetch and parsing."""
        mock_s3_client = MagicMock()
        
        # Mock S3 response
        act_response = {
            'steps': [
                {
                    'response': {
                        'rawProgramBody': 'agentClick("<box>100,200,300,400</box>");'
                    }
                }
            ]
        }
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(act_response).encode('utf-8')
        mock_s3_client.get_object.return_value = {'Body': mock_body}
        
        # Mock parse_nova_act_steps
        expected_cached_steps = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}
        ]
        mock_parse.return_value = expected_cached_steps
        
        result = build_cache.fetch_and_parse_act_response(
            mock_s3_client, 'test-bucket', 'executions/exec_456/act_act_789.json'
        )
        
        assert result == expected_cached_steps
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='executions/exec_456/act_act_789.json'
        )
        mock_parse.assert_called_once_with(act_response)
    
    @patch('build_cache.parse_nova_act_steps')
    def test_parse_returns_none(self, mock_parse):
        """Test handling when parse_nova_act_steps returns None."""
        mock_s3_client = MagicMock()
        
        # Mock S3 response
        act_response = {'steps': []}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(act_response).encode('utf-8')
        mock_s3_client.get_object.return_value = {'Body': mock_body}
        
        # Mock parse_nova_act_steps returning None
        mock_parse.return_value = None
        
        result = build_cache.fetch_and_parse_act_response(
            mock_s3_client, 'test-bucket', 'executions/exec_456/act_act_789.json'
        )
        
        assert result is None
    
    @patch('build_cache.parse_nova_act_steps')
    def test_parse_returns_empty_list(self, mock_parse):
        """Test handling when parse_nova_act_steps returns empty list."""
        mock_s3_client = MagicMock()
        
        # Mock S3 response
        act_response = {'steps': []}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(act_response).encode('utf-8')
        mock_s3_client.get_object.return_value = {'Body': mock_body}
        
        # Mock parse_nova_act_steps returning empty list
        mock_parse.return_value = []
        
        result = build_cache.fetch_and_parse_act_response(
            mock_s3_client, 'test-bucket', 'executions/exec_456/act_act_789.json'
        )
        
        assert result is None
    
    def test_s3_client_error(self):
        """Test handling of S3 ClientError."""
        mock_s3_client = MagicMock()
        mock_s3_client.get_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey', 'Message': 'Key not found'}},
            'GetObject'
        )
        
        result = build_cache.fetch_and_parse_act_response(
            mock_s3_client, 'test-bucket', 'executions/exec_456/act_act_789.json'
        )
        
        assert result is None
    
    def test_json_decode_error(self):
        """Test handling of JSON decode error."""
        mock_s3_client = MagicMock()
        
        # Mock S3 response with invalid JSON
        mock_body = MagicMock()
        mock_body.read.return_value = b'invalid json {'
        mock_s3_client.get_object.return_value = {'Body': mock_body}
        
        result = build_cache.fetch_and_parse_act_response(
            mock_s3_client, 'test-bucket', 'executions/exec_456/act_act_789.json'
        )
        
        assert result is None
    
    @patch('build_cache.parse_nova_act_steps')
    def test_parse_raises_exception(self, mock_parse):
        """Test handling when parse_nova_act_steps raises exception."""
        mock_s3_client = MagicMock()
        
        # Mock S3 response
        act_response = {'steps': []}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(act_response).encode('utf-8')
        mock_s3_client.get_object.return_value = {'Body': mock_body}
        
        # Mock parse_nova_act_steps raising exception
        mock_parse.side_effect = Exception('Parse error')
        
        result = build_cache.fetch_and_parse_act_response(
            mock_s3_client, 'test-bucket', 'executions/exec_456/act_act_789.json'
        )
        
        assert result is None
    
    @patch('build_cache.parse_nova_act_steps')
    def test_s3_access_denied_error(self, mock_parse):
        """Test handling of S3 access denied error."""
        mock_s3_client = MagicMock()
        mock_s3_client.get_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            'GetObject'
        )
        
        result = build_cache.fetch_and_parse_act_response(
            mock_s3_client, 'test-bucket', 'executions/exec_456/act_act_789.json'
        )
        
        assert result is None
    
    @patch('build_cache.parse_nova_act_steps')
    def test_multiple_cached_steps(self, mock_parse):
        """Test successful parsing with multiple cached steps."""
        mock_s3_client = MagicMock()
        
        # Mock S3 response
        act_response = {
            'steps': [
                {'response': {'rawProgramBody': 'agentClick("<box>100,200,300,400</box>");'}},
                {'response': {'rawProgramBody': 'agentType("test", "<box>100,200,300,400</box>");'}}
            ]
        }
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(act_response).encode('utf-8')
        mock_s3_client.get_object.return_value = {'Body': mock_body}
        
        # Mock parse_nova_act_steps
        expected_cached_steps = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}},
            {'type': 'type', 'text': 'test', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}, 'press_enter': False}
        ]
        mock_parse.return_value = expected_cached_steps
        
        result = build_cache.fetch_and_parse_act_response(
            mock_s3_client, 'test-bucket', 'executions/exec_456/act_act_789.json'
        )
        
        assert result == expected_cached_steps
        assert len(result) == 2


class TestUpdateStepCaches:
    """Tests for update_step_caches function."""
    
    def test_successful_batch_update(self, mock_dynamodb_table):
        """Test successful batch update of STEP records."""
        # Mock batch_writer context manager
        mock_batch = MagicMock()
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        step_updates = [
            ('step_1', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}]),
            ('step_2', [{'type': 'type', 'text': 'hello', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}, 'press_enter': False}])
        ]
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 2
        assert failed == 0
        assert mock_batch.put_item.call_count == 2

        # Verify first call
        first_call = mock_batch.put_item.call_args_list[0]
        first_item = first_call[1]['Item']
        assert first_item['pk'] == 'USECASE#uc_123'
        assert first_item['sk'] == 'STEP#step_1'
        assert first_item['cache_last_updated'] == timestamp
        assert 'cached_steps' in first_item

        # Verify cached_steps is JSON string
        cached_steps_1 = json.loads(first_item['cached_steps'])
        assert cached_steps_1[0]['type'] == 'click'

    def test_empty_step_updates_list(self, mock_dynamodb_table):
        """Test handling of empty step_updates list."""
        mock_batch = MagicMock()
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        step_updates = []
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 0
        assert failed == 0
        assert mock_batch.put_item.call_count == 0

    def test_missing_step_id_skipped(self, mock_dynamodb_table):
        """Test that updates with missing step_id are skipped and counted as failed."""
        mock_batch = MagicMock()
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        step_updates = [
            ('step_1', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}]),
            ('', [{'type': 'type', 'text': 'hello'}]),  # Empty step_id
            (None, [{'type': 'navigate', 'url': 'https://example.com'}])  # None step_id
        ]
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 1
        assert failed == 2
        assert mock_batch.put_item.call_count == 1

    def test_json_encoding_error_handled(self, mock_dynamodb_table):
        """Test that JSON encoding errors are handled gracefully."""
        mock_batch = MagicMock()
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        # Create an object that can't be JSON serialized
        class NonSerializable:
            pass

        step_updates = [
            ('step_1', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}]),
            ('step_2', [{'type': 'custom', 'obj': NonSerializable()}])  # Will fail JSON encoding
        ]
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 1
        assert failed == 1
        assert mock_batch.put_item.call_count == 1

    def test_batch_writer_exception_handled(self, mock_dynamodb_table):
        """Test that batch_writer exceptions are handled gracefully."""
        # Mock batch_writer to raise exception
        mock_dynamodb_table.batch_writer.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'Throttled'}},
            'BatchWriteItem'
        )

        step_updates = [
            ('step_1', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}])
        ]
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 0
        assert failed == 1

    def test_individual_put_item_exception_handled(self, mock_dynamodb_table):
        """Test that individual put_item exceptions are handled gracefully."""
        mock_batch = MagicMock()

        # Make put_item raise exception on second call
        def put_item_side_effect(Item):
            if Item['sk'] == 'STEP#step_2':
                raise Exception('DynamoDB error')

        mock_batch.put_item.side_effect = put_item_side_effect
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        step_updates = [
            ('step_1', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}]),
            ('step_2', [{'type': 'type', 'text': 'hello'}]),
            ('step_3', [{'type': 'navigate', 'url': 'https://example.com'}])
        ]
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 2
        assert failed == 1
        assert mock_batch.put_item.call_count == 3

    def test_correct_step_record_key_construction(self, mock_dynamodb_table):
        """Test that STEP record keys are constructed correctly."""
        mock_batch = MagicMock()
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        step_updates = [
            ('my_step_123', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}])
        ]
        timestamp = '2024-01-01T12:00:00.000Z'

        build_cache.update_step_caches(
            mock_dynamodb_table, 'my_usecase_456', step_updates, timestamp
        )

        call_args = mock_batch.put_item.call_args
        item = call_args[1]['Item']

        assert item['pk'] == 'USECASE#my_usecase_456'
        assert item['sk'] == 'STEP#my_step_123'

    def test_cached_steps_serialized_as_json_string(self, mock_dynamodb_table):
        """Test that cached_steps are stored as JSON string."""
        mock_batch = MagicMock()
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        cached_steps = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}},
            {'type': 'type', 'text': 'test', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}, 'press_enter': False}
        ]
        step_updates = [('step_1', cached_steps)]
        timestamp = '2024-01-01T12:00:00.000Z'

        build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        call_args = mock_batch.put_item.call_args
        item = call_args[1]['Item']

        # Verify cached_steps is a string
        assert isinstance(item['cached_steps'], str)

        # Verify it can be deserialized back to original structure
        deserialized = json.loads(item['cached_steps'])
        assert deserialized == cached_steps

    def test_cache_last_updated_timestamp_stored(self, mock_dynamodb_table):
        """Test that cache_last_updated timestamp is stored correctly."""
        mock_batch = MagicMock()
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        step_updates = [
            ('step_1', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}])
        ]
        timestamp = '2024-01-15T14:30:45.123Z'

        build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        call_args = mock_batch.put_item.call_args
        item = call_args[1]['Item']

        assert item['cache_last_updated'] == timestamp

    def test_multiple_steps_with_mixed_success_failure(self, mock_dynamodb_table):
        """Test batch update with mixed success and failure scenarios."""
        mock_batch = MagicMock()

        # Make put_item fail for specific steps
        call_count = [0]
        def put_item_side_effect(Item):
            call_count[0] += 1
            if call_count[0] == 2 or call_count[0] == 4:
                raise Exception('DynamoDB error')

        mock_batch.put_item.side_effect = put_item_side_effect
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        step_updates = [
            ('step_1', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}]),
            ('step_2', [{'type': 'type', 'text': 'hello'}]),  # Will fail
            ('step_3', [{'type': 'navigate', 'url': 'https://example.com'}]),
            ('step_4', [{'type': 'hover', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}]),  # Will fail
            ('step_5', [{'type': 'scroll', 'direction': 'down'}])
        ]
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 3
        assert failed == 2
        assert mock_batch.put_item.call_count == 5

    def test_unexpected_exception_in_batch_writer(self, mock_dynamodb_table):
        """Test handling of unexpected exceptions in batch_writer."""
        mock_dynamodb_table.batch_writer.side_effect = Exception('Unexpected error')

        step_updates = [
            ('step_1', [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}]),
            ('step_2', [{'type': 'type', 'text': 'hello'}])
        ]
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 0
        assert failed == 2

    def test_complex_cached_steps_structure(self, mock_dynamodb_table):
        """Test serialization of complex cached_steps structures."""
        mock_batch = MagicMock()
        mock_dynamodb_table.batch_writer.return_value.__enter__.return_value = mock_batch

        # Complex nested structure
        cached_steps = [
            {
                'type': 'click',
                'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400},
                'metadata': {
                    'confidence': 0.95,
                    'element': 'button',
                    'attributes': ['primary', 'enabled']
                }
            },
            {
                'type': 'type',
                'text': 'test@example.com',
                'bbox': {'x1': 50, 'y1': 100, 'x2': 250, 'y2': 150},
                'press_enter': True,
                'modifiers': ['shift']
            }
        ]
        step_updates = [('step_1', cached_steps)]
        timestamp = '2024-01-01T12:00:00.000Z'

        successful, failed = build_cache.update_step_caches(
            mock_dynamodb_table, 'uc_123', step_updates, timestamp
        )

        assert successful == 1
        assert failed == 0

        call_args = mock_batch.put_item.call_args
        item = call_args[1]['Item']

        # Verify complex structure is preserved
        deserialized = json.loads(item['cached_steps'])
        assert deserialized == cached_steps
        assert deserialized[0]['metadata']['confidence'] == 0.95
        assert deserialized[1]['modifiers'] == ['shift']



class TestLambdaHandler:
    """Tests for lambda_handler function."""
    
    def test_missing_event_fields_returns_200(self, mock_env_vars):
        """Test that Lambda returns 200 when event fields are missing."""
        event = {
            'detail': {
                'usecase_id': 'uc_123'
                # Missing execution_id, execution_status, timestamp
            }
        }
        
        response = build_cache.handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Missing required event fields'
        assert body['stats']['steps_processed'] == 0
    
    def test_non_success_execution_skipped(self, mock_env_vars, valid_event):
        """Test that Lambda skips processing when execution_status is not 'success'."""
        valid_event['detail']['execution_status'] = 'failed'
        
        response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'Skipped' in body['message']
        assert 'failed' in body['message']
    
    def test_missing_environment_variables_returns_200(self, valid_event):
        """Test that Lambda returns 200 when environment variables are missing."""
        with patch.dict(os.environ, {}, clear=True):
            response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Missing environment variables'
    
    @patch('build_cache.boto3')
    def test_cache_disabled_skipped(self, mock_boto3, mock_env_vars, valid_event):
        """Test that Lambda skips processing when cache is disabled."""
        # Mock DynamoDB resource and table
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'pk': 'USECASES',
                'sk': 'USECASE#uc_123',
                'enable_cache': False
            }
        }
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb
        
        response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'Skipped' in body['message']
        assert 'cache not enabled' in body['message']
    
    @patch('build_cache.boto3')
    def test_missing_usecase_record_skipped(self, mock_boto3, mock_env_vars, valid_event):
        """Test that Lambda skips processing when USECASE record doesn't exist."""
        # Mock DynamoDB resource and table
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item in response
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb
        
        response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'Skipped' in body['message']
    
    @patch('build_cache.parse_nova_act_steps')
    @patch('build_cache.boto3')
    def test_cache_enabled_proceeds_to_processing(self, mock_boto3, mock_parse, mock_env_vars, valid_event):
        """Test that Lambda proceeds when cache is enabled and processes steps successfully."""
        # Mock DynamoDB resource and table
        mock_table = MagicMock()
        
        def get_item_side_effect(**kwargs):
            key = kwargs.get('Key', {})
            if key.get('pk') == 'USECASES':
                return {'Item': {'pk': 'USECASES', 'sk': 'USECASE#uc_123', 'enable_cache': True}}
            elif key.get('pk') == 'USECASE#uc_123' and key.get('sk', '').startswith('EXECUTION#'):
                return {'Item': {'pk': 'USECASE#uc_123', 'sk': 'EXECUTION#exec_456', 'nova_session_id': 'session_abc'}}
            return {}
        
        mock_table.get_item.side_effect = get_item_side_effect
        
        # Mock query for execution steps
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_1',
                    'step_id': 'step_1',
                    'step_type': 'navigation',
                    'act_id': 'act_789'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_2',
                    'step_id': 'step_2',
                    'step_type': 'navigation',
                    'act_id': 'act_790'
                }
            ]
        }
        
        # Mock batch_writer
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch_writer
        
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock S3 client
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'executions/exec_456/act_act_789.json'},
                {'Key': 'executions/exec_456/act_act_790.json'}
            ]
        }
        
        # Mock S3 get_object responses
        mock_act_response = {
            'steps': [
                {
                    'response': {
                        'rawProgramBody': 'agentClick("<box>100,200,300,400</box>");'
                    }
                }
            ]
        }
        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(mock_act_response).encode('utf-8'))
        }
        
        # Mock parse_nova_act_steps to return cached steps
        mock_parse.return_value = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}
        ]
        
        # Configure boto3 mock
        mock_boto3.resource.return_value = mock_dynamodb
        mock_boto3.client.return_value = mock_s3_client
        
        response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Cache building completed'
        assert body['stats']['steps_processed'] == 2
        assert body['stats']['successful_updates'] == 2
        assert body['stats']['failed_updates'] == 0
        
        # Verify batch_writer was used
        assert mock_batch_writer.put_item.call_count == 2
    
    def test_unexpected_exception_returns_200(self, mock_env_vars, valid_event):
        """Test that Lambda returns 200 even on unexpected exceptions (fire-and-forget)."""
        with patch('build_cache.boto3.resource', side_effect=Exception('Unexpected error')):
            response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'failed with error' in body['message']
        assert 'error' in body

    @patch('build_cache.parse_nova_act_steps')
    @patch('build_cache.boto3')
    def test_missing_step_id_field_skips_step(self, mock_boto3, mock_parse, mock_env_vars, valid_event):
        """Test that steps with missing step_id field are skipped with error logging."""
        # Mock DynamoDB
        mock_table = MagicMock()
        
        def get_item_side_effect(**kwargs):
            key = kwargs.get('Key', {})
            if key.get('pk') == 'USECASES':
                return {'Item': {'pk': 'USECASES', 'sk': 'USECASE#uc_123', 'enable_cache': True}}
            elif key.get('pk') == 'USECASE#uc_123' and key.get('sk', '').startswith('EXECUTION#'):
                return {'Item': {'pk': 'USECASE#uc_123', 'sk': 'EXECUTION#exec_456', 'nova_session_id': 'session_abc'}}
            return {}
        
        mock_table.get_item.side_effect = get_item_side_effect
        
        # Mock execution steps - one with step_id, one without
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_1',
                    'step_id': 'step_1',  # Has step_id
                    'step_type': 'navigation',
                    'act_id': 'act_789'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_2',
                    # Missing step_id field
                    'step_type': 'navigation',
                    'act_id': 'act_790'
                }
            ]
        }
        
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch_writer
        
        # Mock S3
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'executions/exec_456/act_act_789.json'},
                {'Key': 'executions/exec_456/act_act_790.json'}
            ]
        }
        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps({'steps': []}).encode('utf-8'))
        }
        
        mock_parse.return_value = [{'type': 'click', 'bbox': {}}]
        
        mock_boto3.resource.return_value = MagicMock(Table=lambda x: mock_table)
        mock_boto3.client.return_value = mock_s3_client
        
        response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        # Only 1 step should be successfully updated (the one with step_id)
        assert body['stats']['steps_processed'] == 2
        assert body['stats']['successful_updates'] == 1
        assert body['stats']['failed_updates'] == 0
        
        # Verify only one put_item call (for step with step_id)
        assert mock_batch_writer.put_item.call_count == 1

    @patch('build_cache.parse_nova_act_steps')
    @patch('build_cache.boto3')
    def test_step_level_error_isolation(self, mock_boto3, mock_parse, mock_env_vars, valid_event):
        """Test that individual step failures don't stop processing of remaining steps."""
        # Mock DynamoDB
        mock_table = MagicMock()
        
        def get_item_side_effect(**kwargs):
            key = kwargs.get('Key', {})
            if key.get('pk') == 'USECASES':
                return {'Item': {'pk': 'USECASES', 'sk': 'USECASE#uc_123', 'enable_cache': True}}
            elif key.get('pk') == 'USECASE#uc_123' and key.get('sk', '').startswith('EXECUTION#'):
                return {'Item': {'pk': 'USECASE#uc_123', 'sk': 'EXECUTION#exec_456', 'nova_session_id': 'session_abc'}}
            return {}
        
        mock_table.get_item.side_effect = get_item_side_effect
        
        # Mock execution steps
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_1',
                    'step_id': 'step_1',
                    'step_type': 'navigation',
                    'act_id': 'act_789'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_2',
                    'step_id': 'step_2',
                    'step_type': 'navigation',
                    'act_id': 'act_790'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_3',
                    'step_id': 'step_3',
                    'step_type': 'navigation',
                    'act_id': 'act_791'
                }
            ]
        }
        
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch_writer
        
        # Mock S3 - second get_object call will fail
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'executions/exec_456/act_act_789.json'},
                {'Key': 'executions/exec_456/act_act_790.json'},
                {'Key': 'executions/exec_456/act_act_791.json'}
            ]
        }
        
        # First and third calls succeed, second fails
        mock_s3_client.get_object.side_effect = [
            {'Body': MagicMock(read=lambda: json.dumps({'steps': []}).encode('utf-8'))},
            ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject'),
            {'Body': MagicMock(read=lambda: json.dumps({'steps': []}).encode('utf-8'))}
        ]
        
        mock_parse.return_value = [{'type': 'click', 'bbox': {}}]
        
        mock_boto3.resource.return_value = MagicMock(Table=lambda x: mock_table)
        mock_boto3.client.return_value = mock_s3_client
        
        response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        # All 3 steps processed, but only 2 successful (step 2 failed S3 fetch)
        assert body['stats']['steps_processed'] == 3
        assert body['stats']['successful_updates'] == 2
        assert body['stats']['failed_updates'] == 0
        
        # Verify two put_item calls (steps 1 and 3)
        assert mock_batch_writer.put_item.call_count == 2

    @patch('build_cache.parse_nova_act_steps')
    @patch('build_cache.boto3')
    def test_complete_flow_with_statistics_tracking(self, mock_boto3, mock_parse, mock_env_vars, valid_event):
        """Test complete flow with accurate statistics tracking."""
        # Mock DynamoDB
        mock_table = MagicMock()
        
        def get_item_side_effect(**kwargs):
            key = kwargs.get('Key', {})
            if key.get('pk') == 'USECASES':
                return {'Item': {'pk': 'USECASES', 'sk': 'USECASE#uc_123', 'enable_cache': True}}
            elif key.get('pk') == 'USECASE#uc_123' and key.get('sk', '').startswith('EXECUTION#'):
                return {'Item': {'pk': 'USECASE#uc_123', 'sk': 'EXECUTION#exec_456', 'nova_session_id': 'session_abc'}}
            return {}
        
        mock_table.get_item.side_effect = get_item_side_effect
        
        # Mock execution steps - mix of navigation and assertion steps
        mock_table.query.return_value = {
            'Items': [
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_1',
                    'step_id': 'step_1',
                    'step_type': 'navigation',
                    'act_id': 'act_789'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_2',
                    'step_id': 'step_2',
                    'step_type': 'assertion',  # Not navigation - should be filtered out
                    'act_id': 'act_790'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_3',
                    'step_id': 'step_3',
                    'step_type': 'navigation',
                    'act_id': 'act_791'
                },
                {
                    'pk': 'EXECUTION#exec_456',
                    'sk': 'EXECUTION_STEP#exec_step_4',
                    'step_id': 'step_4',
                    'step_type': 'navigation',
                    # Missing act_id - should be filtered out
                }
            ]
        }
        
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch_writer
        
        # Mock S3
        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'executions/exec_456/act_act_789.json'},
                {'Key': 'executions/exec_456/act_act_791.json'}
            ]
        }
        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps({'steps': []}).encode('utf-8'))
        }
        
        mock_parse.return_value = [{'type': 'click', 'bbox': {}}]
        
        mock_boto3.resource.return_value = MagicMock(Table=lambda x: mock_table)
        mock_boto3.client.return_value = mock_s3_client
        
        response = build_cache.handler(valid_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        # Only 2 navigation steps with act files should be processed
        assert body['stats']['steps_processed'] == 2
        assert body['stats']['successful_updates'] == 2
        assert body['stats']['failed_updates'] == 0
        
        # Verify correct STEP record keys were constructed
        put_item_calls = mock_batch_writer.put_item.call_args_list
        assert len(put_item_calls) == 2
        
        # Check first call
        first_item = put_item_calls[0][1]['Item']
        assert first_item['pk'] == 'USECASE#uc_123'
        assert first_item['sk'] == 'STEP#step_1'
        assert 'cached_steps' in first_item
        assert first_item['cache_last_updated'] == '2024-01-01T12:00:00.000Z'
        
        # Check second call
        second_item = put_item_calls[1][1]['Item']
        assert second_item['pk'] == 'USECASE#uc_123'
        assert second_item['sk'] == 'STEP#step_3'
