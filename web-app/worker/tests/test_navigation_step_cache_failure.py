"""Unit tests for navigation_step cache failure handling (Task 1.3)"""
import pytest
import json
from unittest.mock import Mock, patch
from types import SimpleNamespace
from navigation_step import execute_navigation_step
from cache_executor import CacheExecutionError
from models import ExecutionStep


@pytest.fixture
def mock_nova():
    """Create mock NovaAct instance"""
    nova = Mock()
    nova.page = Mock()
    
    # Mock successful Nova Act result
    result = SimpleNamespace()
    result.metadata = SimpleNamespace()
    result.metadata.act_id = "nova_act_123"
    result.logs = "Nova Act executed successfully"
    nova.act.return_value = result
    
    return nova


@pytest.fixture
def mock_step():
    """Create mock ExecutionStep with cache enabled"""
    step = Mock(spec=ExecutionStep)
    step.sort = 1
    step.instruction = "Click login button"
    step.enable_cache = True
    step.enable_advanced_click_types = False
    step.trajectory_s3_key = None  # No trajectory — allows Playwright cache path
    
    # Valid cached steps JSON
    step.cached_steps = json.dumps([
        {"type": "click", "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 400}}
    ])
    
    return step


class TestCacheExecutionErrorHandling:
    """Test CacheExecutionError is caught and logged correctly"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_execution_error_logs_warning(self, mock_execute, mock_nova, mock_step, caplog):
        """Test CacheExecutionError is caught and warning logged with error details"""
        # Setup: Make execute_cached_steps raise CacheExecutionError
        mock_execute.side_effect = CacheExecutionError("Element not found at bbox")
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify warning logged with error details
        assert "Cache execution failed for step 1" in caplog.text
        assert "Element not found at bbox" in caplog.text
        assert "falling back to Nova Act" in caplog.text
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_execution_error_falls_back_to_nova_act(self, mock_execute, mock_nova, mock_step):
        """Test CacheExecutionError triggers fallback to Nova Act"""
        # Setup: Make execute_cached_steps raise CacheExecutionError
        mock_execute.side_effect = CacheExecutionError("Click failed")
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify Nova Act was called as fallback
        mock_nova.act.assert_called_once_with("Click login button")
        
        # Verify Nova Act result returned
        assert result.metadata.act_id == "nova_act_123"
        assert success is True
        assert logs == ""


class TestJSONDecodeErrorHandling:
    """Test JSONDecodeError is caught and logged correctly"""
    
    def test_json_decode_error_logs_warning(self, mock_nova, mock_step, caplog):
        """Test JSONDecodeError is caught and warning logged with parse error"""
        # Setup: Invalid JSON in cached_steps
        mock_step.cached_steps = "not valid json {["
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify warning logged with parse error
        assert "Failed to parse cached_steps for step 1" in caplog.text
        assert "falling back to Nova Act" in caplog.text
    
    def test_json_decode_error_falls_back_to_nova_act(self, mock_nova, mock_step):
        """Test JSONDecodeError triggers fallback to Nova Act"""
        # Setup: Invalid JSON
        mock_step.cached_steps = "invalid json"
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify Nova Act was called as fallback
        mock_nova.act.assert_called_once_with("Click login button")
        
        # Verify Nova Act result returned
        assert result.metadata.act_id == "nova_act_123"
        assert success is True


class TestGeneralExceptionHandling:
    """Test general Exception is caught and logged correctly"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_unexpected_exception_logs_warning(self, mock_execute, mock_nova, mock_step, caplog):
        """Test unexpected exception is caught and warning logged"""
        # Setup: Make execute_cached_steps raise unexpected exception
        mock_execute.side_effect = RuntimeError("Unexpected error")
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify warning logged with error details
        assert "Unexpected error during cache execution for step 1" in caplog.text
        assert "Unexpected error" in caplog.text
        assert "falling back to Nova Act" in caplog.text
    
    @patch('navigation_step.execute_cached_steps')
    def test_unexpected_exception_falls_back_to_nova_act(self, mock_execute, mock_nova, mock_step):
        """Test unexpected exception triggers fallback to Nova Act"""
        # Setup: Raise unexpected exception
        mock_execute.side_effect = ValueError("Something went wrong")
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify Nova Act was called as fallback
        mock_nova.act.assert_called_once_with("Click login button")
        
        # Verify Nova Act result returned
        assert result.metadata.act_id == "nova_act_123"
        assert success is True
    
    @patch('navigation_step.json.loads')
    def test_json_loads_exception_falls_back(self, mock_json_loads, mock_nova, mock_step):
        """Test exception during json.loads triggers fallback"""
        # Setup: Make json.loads raise exception
        mock_json_loads.side_effect = TypeError("Unexpected type error")
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify Nova Act was called as fallback
        mock_nova.act.assert_called_once()


class TestFallbackExecutionCorrectness:
    """Test fallback execution maintains correct behavior"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_fallback_preserves_instruction(self, mock_execute, mock_nova, mock_step):
        """Test fallback uses original instruction"""
        mock_execute.side_effect = CacheExecutionError("Cache failed")
        
        # Execute
        execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify instruction passed to Nova Act unchanged
        mock_nova.act.assert_called_once_with("Click login button")
    
    @patch('navigation_step.execute_cached_steps')
    def test_fallback_with_advanced_click_types(self, mock_execute, mock_nova, mock_step):
        """Test fallback includes click_base_prompt when advanced click types enabled"""
        mock_execute.side_effect = CacheExecutionError("Cache failed")
        mock_step.enable_advanced_click_types = True
        
        # Execute
        execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify instruction includes click_base_prompt
        call_args = mock_nova.act.call_args[0][0]
        assert "agentClick" in call_args
        assert "clickType" in call_args
        assert "Click login button" in call_args
    
    @patch('navigation_step.execute_cached_steps')
    def test_fallback_returns_nova_act_result_unchanged(self, mock_execute, mock_nova, mock_step):
        """Test fallback returns Nova Act result object unchanged"""
        mock_execute.side_effect = CacheExecutionError("Cache failed")
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify Nova Act result returned unchanged
        assert result.metadata.act_id == "nova_act_123"
        assert result.logs == "Nova Act executed successfully"
        assert success is True
        assert logs == ""


class TestMultipleExceptionTypes:
    """Test different exception types are handled correctly"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_execution_error_takes_precedence(self, mock_execute, mock_nova, mock_step, caplog):
        """Test CacheExecutionError is caught by specific handler"""
        mock_execute.side_effect = CacheExecutionError("Specific cache error")
        
        execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify specific CacheExecutionError message
        assert "Cache execution failed for step 1" in caplog.text
        assert "Specific cache error" in caplog.text
    
    def test_json_decode_error_takes_precedence(self, mock_nova, mock_step, caplog):
        """Test JSONDecodeError is caught by specific handler"""
        mock_step.cached_steps = '{"invalid": json}'
        
        execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify specific JSONDecodeError message
        assert "Failed to parse cached_steps for step 1" in caplog.text
    
    @patch('navigation_step.execute_cached_steps')
    def test_other_exceptions_caught_by_general_handler(self, mock_execute, mock_nova, mock_step, caplog):
        """Test other exceptions caught by general Exception handler"""
        mock_execute.side_effect = KeyError("Missing key")
        
        execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify general exception message
        assert "Unexpected error during cache execution for step 1" in caplog.text
        assert "Missing key" in caplog.text


class TestNoExceptionWhenCacheDisabled:
    """Test no exception handling when cache is disabled"""
    
    def test_cache_disabled_skips_exception_handling(self, mock_nova, mock_step):
        """Test cache disabled goes directly to Nova Act without exception handling"""
        mock_step.enable_cache = False
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, False)
        
        # Verify Nova Act called directly
        mock_nova.act.assert_called_once_with("Click login button")
        assert result.metadata.act_id == "nova_act_123"
    
    def test_no_cached_steps_skips_exception_handling(self, mock_nova, mock_step):
        """Test missing cached_steps goes directly to Nova Act"""
        mock_step.cached_steps = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify Nova Act called directly
        mock_nova.act.assert_called_once_with("Click login button")
        assert result.metadata.act_id == "nova_act_123"
