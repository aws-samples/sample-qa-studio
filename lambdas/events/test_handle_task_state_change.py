"""
Unit tests for handle_task_state_change Lambda function.

Tests the suite execution tracking functionality added to the event handler.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'endpoints'))

import pytest
from unittest.mock import Mock, patch, MagicMock
from handle_task_state_change import (
    query_suite_execution_results,
    update_suite_execution_result,
    update_suite_execution_counters,
    check_suite_completion,
    update_suite_execution_tracking
)


class TestQuerySuiteExecutionResults:
    """Test query_suite_execution_results function."""
    
    def test_finds_results_by_usecase_execution_id(self):
        """Test finding suite execution results by usecase_execution_id."""
        mock_client = Mock()
        mock_client.scan.return_value = {
            'Items': [
                {
                    'pk': {'S': 'SUITE_EXEC#exec-123'},
                    'sk': {'S': 'RESULT#usecase-456'},
                    'suite_execution_id': {'S': 'exec-123'},
                    'usecase_id': {'S': 'usecase-456'},
                    'usecase_execution_id': {'S': 'uc-exec-789'},
                    'status': {'S': 'running'}
                }
            ]
        }
        
        results = query_suite_execution_results(
            mock_client, 'test-table', 'uc-exec-789'
        )
        
        assert len(results) == 1
        assert results[0]['suite_execution_id']['S'] == 'exec-123'
        assert results[0]['usecase_id']['S'] == 'usecase-456'
    
    def test_fallback_to_usecase_id_lookup(self):
        """Test fallback to finding by usecase_id when usecase_execution_id not stored."""
        mock_client = Mock()
        
        # First scan returns no results (no usecase_execution_id match)
        # Second scan finds the execution
        # Third scan finds suite results by usecase_id
        mock_client.scan.side_effect = [
            {'Items': []},  # No results by usecase_execution_id
            {  # Find execution to get usecase_id
                'Items': [{
                    'pk': {'S': 'USECASE_EXECUTION#usecase-456'},
                    'sk': {'S': 'EXECUTION#uc-exec-789'}
                }]
            },
            {  # Find suite results by usecase_id
                'Items': [{
                    'pk': {'S': 'SUITE_EXEC#exec-123'},
                    'sk': {'S': 'RESULT#usecase-456'},
                    'suite_execution_id': {'S': 'exec-123'},
                    'usecase_id': {'S': 'usecase-456'},
                    'status': {'S': 'pending'}
                }]
            }
        ]
        
        results = query_suite_execution_results(
            mock_client, 'test-table', 'uc-exec-789'
        )
        
        assert len(results) == 1
        assert results[0]['usecase_id']['S'] == 'usecase-456'
        assert mock_client.scan.call_count == 3
    
    def test_returns_empty_when_not_found(self):
        """Test returns empty list when no suite execution results found."""
        mock_client = Mock()
        mock_client.scan.side_effect = [
            {'Items': []},  # No results by usecase_execution_id
            {'Items': []},  # Execution not found
        ]
        
        results = query_suite_execution_results(
            mock_client, 'test-table', 'uc-exec-789'
        )
        
        assert len(results) == 0
    
    def test_handles_scan_error_gracefully(self):
        """Test handles DynamoDB scan errors gracefully."""
        mock_client = Mock()
        mock_client.scan.side_effect = Exception("DynamoDB error")
        
        results = query_suite_execution_results(
            mock_client, 'test-table', 'uc-exec-789'
        )
        
        assert len(results) == 0


class TestUpdateSuiteExecutionResult:
    """Test update_suite_execution_result function."""
    
    def test_updates_result_status_success(self):
        """Test updating suite execution result to success status."""
        mock_client = Mock()
        
        success = update_suite_execution_result(
            mock_client, 'test-table', 'exec-123', 'usecase-456',
            'success', '2024-01-01T00:00:00Z'
        )
        
        assert success is True
        mock_client.update_item.assert_called_once()
        call_args = mock_client.update_item.call_args
        assert call_args[1]['Key']['pk']['S'] == 'SUITE_EXEC#exec-123'
        assert call_args[1]['Key']['sk']['S'] == 'RESULT#usecase-456'
        assert ':status' in call_args[1]['ExpressionAttributeValues']
        assert call_args[1]['ExpressionAttributeValues'][':status']['S'] == 'success'
    
    def test_updates_result_with_error_message(self):
        """Test updating suite execution result with error message."""
        mock_client = Mock()
        
        success = update_suite_execution_result(
            mock_client, 'test-table', 'exec-123', 'usecase-456',
            'failed', '2024-01-01T00:00:00Z', 'Task failed'
        )
        
        assert success is True
        call_args = mock_client.update_item.call_args
        assert ':error_msg' in call_args[1]['ExpressionAttributeValues']
        assert call_args[1]['ExpressionAttributeValues'][':error_msg']['S'] == 'Task failed'
    
    def test_handles_update_error_gracefully(self):
        """Test handles DynamoDB update errors gracefully."""
        mock_client = Mock()
        mock_client.update_item.side_effect = Exception("DynamoDB error")
        
        success = update_suite_execution_result(
            mock_client, 'test-table', 'exec-123', 'usecase-456',
            'success', '2024-01-01T00:00:00Z'
        )
        
        assert success is False


class TestUpdateSuiteExecutionCounters:
    """Test update_suite_execution_counters function."""
    
    def test_updates_counters_for_success(self):
        """Test updating counters when use case succeeds."""
        mock_client = Mock()
        
        success = update_suite_execution_counters(
            mock_client, 'test-table', 'suite-123', 'exec-456', 'success'
        )
        
        assert success is True
        call_args = mock_client.update_item.call_args
        assert 'completed_usecases' in call_args[1]['UpdateExpression']
        assert 'successful_usecases' in call_args[1]['UpdateExpression']
        assert 'running_usecases' in call_args[1]['UpdateExpression']
        assert call_args[1]['ExpressionAttributeValues'][':inc']['N'] == '1'
        assert call_args[1]['ExpressionAttributeValues'][':dec']['N'] == '-1'
    
    def test_updates_counters_for_failure(self):
        """Test updating counters when use case fails."""
        mock_client = Mock()
        
        success = update_suite_execution_counters(
            mock_client, 'test-table', 'suite-123', 'exec-456', 'failed'
        )
        
        assert success is True
        call_args = mock_client.update_item.call_args
        assert 'completed_usecases' in call_args[1]['UpdateExpression']
        assert 'failed_usecases' in call_args[1]['UpdateExpression']
        assert 'running_usecases' in call_args[1]['UpdateExpression']
    
    def test_updates_counters_for_stopped(self):
        """Test updating counters when use case is stopped (treated as failed)."""
        mock_client = Mock()
        
        success = update_suite_execution_counters(
            mock_client, 'test-table', 'suite-123', 'exec-456', 'stopped'
        )
        
        assert success is True
        call_args = mock_client.update_item.call_args
        assert 'completed_usecases' in call_args[1]['UpdateExpression']
        assert 'failed_usecases' in call_args[1]['UpdateExpression']
        assert 'running_usecases' in call_args[1]['UpdateExpression']
        # Verify stopped is treated as failed
        assert call_args[1]['ExpressionAttributeValues'][':inc']['N'] == '1'
        assert call_args[1]['ExpressionAttributeValues'][':dec']['N'] == '-1'
    
    def test_handles_unknown_status(self):
        """Test handles unknown status gracefully."""
        mock_client = Mock()
        
        success = update_suite_execution_counters(
            mock_client, 'test-table', 'suite-123', 'exec-456', 'unknown'
        )
        
        assert success is False
        mock_client.update_item.assert_not_called()
    
    def test_handles_update_error_gracefully(self):
        """Test handles DynamoDB update errors gracefully."""
        mock_client = Mock()
        mock_client.update_item.side_effect = Exception("DynamoDB error")
        
        success = update_suite_execution_counters(
            mock_client, 'test-table', 'suite-123', 'exec-456', 'success'
        )
        
        assert success is False


class TestCheckSuiteCompletion:
    """Test check_suite_completion function."""
    
    def test_suite_not_complete_yet(self):
        """Test suite execution not complete when use cases still running."""
        mock_client = Mock()
        mock_client.get_item.return_value = {
            'Item': {
                'total_usecases': {'N': '5'},
                'completed_usecases': {'N': '3'},
                'successful_usecases': {'N': '3'},
                'failed_usecases': {'N': '0'}
            }
        }
        
        result = check_suite_completion(
            mock_client, 'test-table', 'suite-123', 'exec-456'
        )
        
        assert result is False
        # Should not update status
        assert mock_client.update_item.call_count == 0
    
    def test_suite_complete_all_success(self):
        """Test suite execution complete with all use cases successful."""
        mock_client = Mock()
        mock_client.get_item.return_value = {
            'Item': {
                'total_usecases': {'N': '5'},
                'completed_usecases': {'N': '5'},
                'successful_usecases': {'N': '5'},
                'failed_usecases': {'N': '0'}
            }
        }
        
        with patch('handle_task_state_change.get_current_timestamp', return_value='2024-01-01T00:00:00Z'):
            result = check_suite_completion(
                mock_client, 'test-table', 'suite-123', 'exec-456'
            )
        
        assert result is True
        call_args = mock_client.update_item.call_args
        assert call_args[1]['ExpressionAttributeValues'][':status']['S'] == 'completed'
    
    def test_suite_complete_partial_success(self):
        """Test suite execution complete with some failures."""
        mock_client = Mock()
        mock_client.get_item.return_value = {
            'Item': {
                'total_usecases': {'N': '5'},
                'completed_usecases': {'N': '5'},
                'successful_usecases': {'N': '3'},
                'failed_usecases': {'N': '2'}
            }
        }
        
        with patch('handle_task_state_change.get_current_timestamp', return_value='2024-01-01T00:00:00Z'):
            result = check_suite_completion(
                mock_client, 'test-table', 'suite-123', 'exec-456'
            )
        
        assert result is True
        call_args = mock_client.update_item.call_args
        assert call_args[1]['ExpressionAttributeValues'][':status']['S'] == 'partial'
    
    def test_suite_complete_all_failed(self):
        """Test suite execution complete with all use cases failed."""
        mock_client = Mock()
        mock_client.get_item.return_value = {
            'Item': {
                'total_usecases': {'N': '5'},
                'completed_usecases': {'N': '5'},
                'successful_usecases': {'N': '0'},
                'failed_usecases': {'N': '5'}
            }
        }
        
        with patch('handle_task_state_change.get_current_timestamp', return_value='2024-01-01T00:00:00Z'):
            result = check_suite_completion(
                mock_client, 'test-table', 'suite-123', 'exec-456'
            )
        
        assert result is True
        call_args = mock_client.update_item.call_args
        assert call_args[1]['ExpressionAttributeValues'][':status']['S'] == 'failed'
    
    def test_handles_missing_suite_execution(self):
        """Test handles missing suite execution gracefully."""
        mock_client = Mock()
        mock_client.get_item.return_value = {}
        
        result = check_suite_completion(
            mock_client, 'test-table', 'suite-123', 'exec-456'
        )
        
        assert result is False
    
    def test_handles_get_error_gracefully(self):
        """Test handles DynamoDB get errors gracefully."""
        mock_client = Mock()
        mock_client.get_item.side_effect = Exception("DynamoDB error")
        
        result = check_suite_completion(
            mock_client, 'test-table', 'suite-123', 'exec-456'
        )
        
        assert result is False


class TestUpdateSuiteExecutionTracking:
    """Test update_suite_execution_tracking integration function."""
    
    @patch('handle_task_state_change.query_suite_execution_results')
    @patch('handle_task_state_change.update_suite_execution_result')
    @patch('handle_task_state_change.update_suite_execution_counters')
    @patch('handle_task_state_change.check_suite_completion')
    def test_updates_suite_execution_when_found(
        self, mock_check, mock_counters, mock_result, mock_query
    ):
        """Test updates suite execution when use case is part of a suite."""
        mock_client = Mock()
        
        # Mock query to return a suite execution result
        mock_query.return_value = [{
            'suite_execution_id': {'S': 'exec-123'},
            'usecase_id': {'S': 'usecase-456'}
        }]
        
        # Mock scan to return suite execution with suite_id
        mock_client.scan.return_value = {
            'Items': [{
                'suite_id': {'S': 'suite-789'},
                'id': {'S': 'exec-123'}
            }]
        }
        
        update_suite_execution_tracking(
            mock_client, 'test-table', 'uc-exec-999',
            'success', '2024-01-01T00:00:00Z'
        )
        
        # Verify all functions were called
        mock_query.assert_called_once()
        mock_result.assert_called_once()
        mock_counters.assert_called_once()
        mock_check.assert_called_once()
    
    @patch('handle_task_state_change.query_suite_execution_results')
    def test_does_nothing_when_not_part_of_suite(self, mock_query):
        """Test does nothing when use case execution is not part of a suite."""
        mock_client = Mock()
        mock_query.return_value = []
        
        update_suite_execution_tracking(
            mock_client, 'test-table', 'uc-exec-999',
            'success', '2024-01-01T00:00:00Z'
        )
        
        # Should only call query, nothing else
        mock_query.assert_called_once()
        mock_client.update_item.assert_not_called()
    
    @patch('handle_task_state_change.query_suite_execution_results')
    def test_handles_errors_gracefully(self, mock_query):
        """Test handles errors gracefully without raising exceptions."""
        mock_client = Mock()
        mock_query.side_effect = Exception("Query error")
        
        # Should not raise exception
        update_suite_execution_tracking(
            mock_client, 'test-table', 'uc-exec-999',
            'success', '2024-01-01T00:00:00Z'
        )
    
    @patch('handle_task_state_change.query_suite_execution_results')
    @patch('handle_task_state_change.update_suite_execution_result')
    def test_continues_on_partial_failure(self, mock_result, mock_query):
        """Test continues processing even if one suite update fails."""
        mock_client = Mock()
        
        # Return two suite execution results
        mock_query.return_value = [
            {
                'suite_execution_id': {'S': 'exec-123'},
                'usecase_id': {'S': 'usecase-456'}
            },
            {
                'suite_execution_id': {'S': 'exec-789'},
                'usecase_id': {'S': 'usecase-456'}
            }
        ]
        
        # First scan succeeds, second fails
        mock_client.scan.side_effect = [
            {'Items': [{'suite_id': {'S': 'suite-111'}, 'id': {'S': 'exec-123'}}]},
            Exception("Scan error")
        ]
        
        # Should not raise exception
        update_suite_execution_tracking(
            mock_client, 'test-table', 'uc-exec-999',
            'success', '2024-01-01T00:00:00Z'
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
