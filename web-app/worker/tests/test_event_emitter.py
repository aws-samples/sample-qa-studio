"""Unit tests for event_emitter module."""

import json
import logging
from datetime import datetime
from unittest import mock

import pytest
from botocore.exceptions import ClientError

from event_emitter import emit_execution_completed_event


class TestSuccessfulEventEmission:
    """Tests for successful event emission scenarios."""
    
    @mock.patch('boto3.client')
    def test_emit_event_success_status(self, mock_boto_client, caplog):
        """Test successful event emission with success status."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute
        with caplog.at_level(logging.INFO):
            emit_execution_completed_event('uc_123', 'exec_456', 'success', 'us-east-1')
        
        # Verify EventBridge client was created with correct region
        mock_boto_client.assert_called_once_with('events', region_name='us-east-1')
        
        # Verify put_events was called
        assert mock_eventbridge.put_events.called
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        
        # Verify event structure
        assert len(entries) == 1
        event = entries[0]
        assert event['Source'] == 'qa-studio.worker'
        assert event['DetailType'] == 'usecase.execution.completed'
        
        # Verify event detail
        detail = json.loads(event['Detail'])
        assert detail['usecase_id'] == 'uc_123'
        assert detail['execution_id'] == 'exec_456'
        assert detail['execution_status'] == 'success'
        assert 'timestamp' in detail
        
        # Verify logging
        assert 'Emitted execution completed event: uc_123/exec_456 -> success' in caplog.text
    
    @mock.patch('boto3.client')
    def test_emit_event_failed_status(self, mock_boto_client, caplog):
        """Test successful event emission with failed status."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute
        with caplog.at_level(logging.INFO):
            emit_execution_completed_event('uc_789', 'exec_012', 'failed', 'us-west-2')
        
        # Verify put_events was called
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        detail = json.loads(entries[0]['Detail'])
        
        assert detail['execution_status'] == 'failed'
        assert 'Emitted execution completed event: uc_789/exec_012 -> failed' in caplog.text
    
    @mock.patch('boto3.client')
    def test_emit_event_without_region(self, mock_boto_client):
        """Test event emission without explicit region (uses default)."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute
        emit_execution_completed_event('uc_123', 'exec_456', 'success')
        
        # Verify EventBridge client was created without region parameter
        mock_boto_client.assert_called_once_with('events')


class TestEventStructure:
    """Tests for event structure validation."""
    
    @mock.patch('boto3.client')
    def test_event_has_all_required_fields(self, mock_boto_client):
        """Verify event contains all required fields."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute
        emit_execution_completed_event('uc_test', 'exec_test', 'success', 'us-east-1')
        
        # Get the event
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        event = entries[0]
        detail = json.loads(event['Detail'])
        
        # Verify all required fields are present and non-empty
        assert event['Source'] == 'qa-studio.worker'
        assert event['DetailType'] == 'usecase.execution.completed'
        assert detail['usecase_id'] == 'uc_test'
        assert detail['execution_id'] == 'exec_test'
        assert detail['execution_status'] == 'success'
        assert detail['timestamp']
        assert len(detail['timestamp']) > 0
    
    @mock.patch('boto3.client')
    def test_timestamp_format_iso8601(self, mock_boto_client):
        """Verify timestamp is in ISO 8601 format with UTC timezone."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute
        emit_execution_completed_event('uc_123', 'exec_456', 'success')
        
        # Get the timestamp
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        detail = json.loads(entries[0]['Detail'])
        timestamp = detail['timestamp']
        
        # Verify format: YYYY-MM-DDTHH:MM:SS.ffffffZ
        assert timestamp.endswith('Z')
        assert 'T' in timestamp
        
        # Verify it's parseable
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        assert isinstance(parsed, datetime)
    
    @mock.patch('boto3.client')
    def test_detail_is_valid_json(self, mock_boto_client):
        """Verify event detail is valid JSON."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute
        emit_execution_completed_event('uc_123', 'exec_456', 'success')
        
        # Get the detail
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        detail_str = entries[0]['Detail']
        
        # Verify it's valid JSON
        detail = json.loads(detail_str)
        assert isinstance(detail, dict)


class TestErrorHandling:
    """Tests for error handling and fire-and-forget behavior."""
    
    @mock.patch('boto3.client')
    def test_client_initialization_failure(self, mock_boto_client, caplog):
        """Test handling of EventBridge client initialization failure."""
        # Setup mock to raise exception
        mock_boto_client.side_effect = Exception('Client initialization failed')
        
        # Execute - should not raise exception
        with caplog.at_level(logging.ERROR):
            emit_execution_completed_event('uc_123', 'exec_456', 'success')
        
        # Verify error was logged
        assert 'Failed to initialize EventBridge client' in caplog.text
        assert 'Client initialization failed' in caplog.text
    
    @mock.patch('boto3.client')
    def test_put_events_client_error(self, mock_boto_client, caplog):
        """Test handling of ClientError during put_events."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Make put_events raise ClientError
        error_response = {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}}
        mock_eventbridge.put_events.side_effect = ClientError(error_response, 'PutEvents')
        
        # Execute - should not raise exception
        with caplog.at_level(logging.ERROR):
            emit_execution_completed_event('uc_123', 'exec_456', 'success')
        
        # Verify error was logged
        assert 'Failed to emit execution completed event' in caplog.text
    
    @mock.patch('boto3.client')
    def test_put_events_generic_exception(self, mock_boto_client, caplog):
        """Test handling of generic exception during put_events."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Make put_events raise generic exception
        mock_eventbridge.put_events.side_effect = Exception('Network error')
        
        # Execute - should not raise exception
        with caplog.at_level(logging.ERROR):
            emit_execution_completed_event('uc_123', 'exec_456', 'failed')
        
        # Verify error was logged
        assert 'Failed to emit execution completed event' in caplog.text
        assert 'Network error' in caplog.text
    
    @mock.patch('boto3.client')
    def test_function_never_raises_exception(self, mock_boto_client):
        """Verify function never raises exceptions (fire-and-forget)."""
        # Test various failure scenarios
        test_cases = [
            Exception('Client init failed'),
            ClientError({'Error': {'Code': 'Error', 'Message': 'msg'}}, 'op'),
            RuntimeError('Runtime error'),
            ValueError('Value error')
        ]
        
        for exception in test_cases:
            mock_boto_client.side_effect = exception
            
            # Should not raise any exception
            try:
                emit_execution_completed_event('uc_123', 'exec_456', 'success')
            except Exception as e:
                pytest.fail(f"Function raised exception: {e}")


class TestLogging:
    """Tests for logging behavior."""
    
    @mock.patch('boto3.client')
    def test_info_logging_on_success(self, mock_boto_client, caplog):
        """Verify INFO level logging on successful emission."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute
        with caplog.at_level(logging.INFO):
            emit_execution_completed_event('uc_abc', 'exec_xyz', 'success')
        
        # Verify INFO log contains required information
        info_logs = [record for record in caplog.records if record.levelname == 'INFO']
        assert len(info_logs) == 1
        assert 'uc_abc' in info_logs[0].message
        assert 'exec_xyz' in info_logs[0].message
        assert 'success' in info_logs[0].message
    
    @mock.patch('boto3.client')
    def test_error_logging_on_client_failure(self, mock_boto_client, caplog):
        """Verify ERROR level logging on client initialization failure."""
        # Setup mock to fail
        mock_boto_client.side_effect = Exception('Init failed')
        
        # Execute
        with caplog.at_level(logging.ERROR):
            emit_execution_completed_event('uc_123', 'exec_456', 'success')
        
        # Verify ERROR log
        error_logs = [record for record in caplog.records if record.levelname == 'ERROR']
        assert len(error_logs) == 1
        assert 'Failed to initialize EventBridge client' in error_logs[0].message
    
    @mock.patch('boto3.client')
    def test_error_logging_on_emission_failure(self, mock_boto_client, caplog):
        """Verify ERROR level logging on emission failure."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        mock_eventbridge.put_events.side_effect = Exception('Emission failed')
        
        # Execute
        with caplog.at_level(logging.ERROR):
            emit_execution_completed_event('uc_123', 'exec_456', 'failed')
        
        # Verify ERROR log
        error_logs = [record for record in caplog.records if record.levelname == 'ERROR']
        assert len(error_logs) == 1
        assert 'Failed to emit execution completed event' in error_logs[0].message
    
    @mock.patch('boto3.client')
    def test_debug_logging_includes_event_detail(self, mock_boto_client, caplog):
        """Verify DEBUG level logging includes full event detail."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute with DEBUG logging
        with caplog.at_level(logging.DEBUG):
            emit_execution_completed_event('uc_123', 'exec_456', 'success')
        
        # Verify DEBUG log contains event detail JSON
        debug_logs = [record for record in caplog.records if record.levelname == 'DEBUG']
        assert len(debug_logs) == 1
        assert 'Event detail:' in debug_logs[0].message
        assert 'uc_123' in debug_logs[0].message
        assert 'exec_456' in debug_logs[0].message


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    @mock.patch('boto3.client')
    def test_empty_string_ids(self, mock_boto_client):
        """Test with empty string IDs."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute
        emit_execution_completed_event('', '', 'success')
        
        # Verify event was still emitted
        assert mock_eventbridge.put_events.called
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        detail = json.loads(entries[0]['Detail'])
        
        assert detail['usecase_id'] == ''
        assert detail['execution_id'] == ''
    
    @mock.patch('boto3.client')
    def test_special_characters_in_ids(self, mock_boto_client):
        """Test with special characters in IDs."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute with special characters
        emit_execution_completed_event(
            'uc_test-123_abc',
            'exec_test-456_xyz',
            'success'
        )
        
        # Verify event was emitted correctly
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        detail = json.loads(entries[0]['Detail'])
        
        assert detail['usecase_id'] == 'uc_test-123_abc'
        assert detail['execution_id'] == 'exec_test-456_xyz'
    
    @mock.patch('boto3.client')
    def test_long_ids(self, mock_boto_client):
        """Test with very long IDs."""
        # Setup mock
        mock_eventbridge = mock.Mock()
        mock_boto_client.return_value = mock_eventbridge
        
        # Execute with long IDs
        long_id = 'a' * 1000
        emit_execution_completed_event(long_id, long_id, 'success')
        
        # Verify event was emitted
        assert mock_eventbridge.put_events.called
