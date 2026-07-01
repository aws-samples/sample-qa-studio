"""Unit tests for navigation_step successful cache execution (Task 2.1)"""
import pytest
import json
import logging
from unittest.mock import Mock, patch
from types import SimpleNamespace
from navigation_step import execute_navigation_step
from models import ExecutionStep


@pytest.fixture
def mock_nova():
    """Create mock NovaAct instance"""
    nova = Mock()
    nova.page = Mock()
    
    # Mock successful Nova Act result (for fallback scenarios)
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


class TestSuccessfulCacheExecution:
    """Test successful cache execution returns correct result structure"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_returns_correct_structure(self, mock_execute, mock_nova, mock_step):
        """Test cache hit returns (result, True, "") tuple"""
        # Setup: Mock successful cache execution
        mock_execute.return_value = None  # Success
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify return signature
        assert success is True
        assert logs == ""
        assert result is not None
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_result_has_metadata_act_id(self, mock_execute, mock_nova, mock_step):
        """Test cache result has metadata.act_id='cached'"""
        # Setup: Mock successful cache execution
        mock_execute.return_value = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify result structure
        assert hasattr(result, 'metadata')
        assert hasattr(result.metadata, 'act_id')
        assert result.metadata.act_id == "cached"
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_result_has_empty_logs(self, mock_execute, mock_nova, mock_step):
        """Test cache result has logs=''"""
        # Setup: Mock successful cache execution
        mock_execute.return_value = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify result has empty logs attribute
        assert hasattr(result, 'logs')
        assert result.logs == ""


class TestNovaActNotCalledOnCacheHit:
    """Test Nova Act is not called when cache execution succeeds"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_nova_act_not_called_on_cache_success(self, mock_execute, mock_nova, mock_step):
        """Test nova.act() is not called when cache succeeds"""
        # Setup: Mock successful cache execution
        mock_execute.return_value = None
        
        # Execute
        execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify Nova Act was NOT called
        mock_nova.act.assert_not_called()
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_skips_nova_act_entirely(self, mock_execute, mock_nova, mock_step):
        """Test cache hit path returns before Nova Act code"""
        # Setup: Mock successful cache execution
        mock_execute.return_value = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify Nova Act not called and cache result returned
        mock_nova.act.assert_not_called()
        assert result.metadata.act_id == "cached"


class TestCacheExecutionIntegration:
    """Test execute_cached_steps is called with correct arguments"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_execute_cached_steps_called_with_nova(self, mock_execute, mock_nova, mock_step):
        """Test execute_cached_steps receives NovaAct instance"""
        # Setup
        mock_execute.return_value = None
        
        # Execute
        execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify execute_cached_steps called with nova
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0]
        assert call_args[0] is mock_nova
    
    @patch('navigation_step.execute_cached_steps')
    def test_execute_cached_steps_called_with_parsed_steps(self, mock_execute, mock_nova, mock_step):
        """Test execute_cached_steps receives parsed cached_steps list"""
        # Setup
        mock_execute.return_value = None
        
        # Execute
        execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify execute_cached_steps called with parsed steps
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0]
        parsed_steps = call_args[1]
        
        # Verify it's a list with correct structure
        assert isinstance(parsed_steps, list)
        assert len(parsed_steps) == 1
        assert parsed_steps[0]["type"] == "click"
        assert parsed_steps[0]["bbox"] == {"x1": 100, "y1": 200, "x2": 300, "y2": 400}


class TestCacheHitLogging:
    """Test cache hit logs correct INFO messages"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_logs_info_message(self, mock_execute, mock_nova, mock_step, caplog):
        """Test cache hit logs INFO message with 'Cache hit'"""
        # Setup
        mock_execute.return_value = None
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify INFO log contains "Cache hit"
        assert "Cache hit for step 1" in caplog.text
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_logs_step_sort(self, mock_execute, mock_nova, mock_step, caplog):
        """Test cache hit log includes step sort number"""
        # Setup: Different step sort
        mock_step.sort = 5
        mock_execute.return_value = None
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify step sort in log message
        assert "Cache hit for step 5" in caplog.text
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_logs_duration(self, mock_execute, mock_nova, mock_step, caplog):
        """Test cache hit log includes execution duration in milliseconds"""
        # Setup
        mock_execute.return_value = None
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify duration in log message (format: "executed in XXXms")
        assert "executed in" in caplog.text
        assert "ms)" in caplog.text


class TestCacheHitWithMultipleSteps:
    """Test cache hit with multiple cached steps"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_with_multiple_actions(self, mock_execute, mock_nova, mock_step):
        """Test cache hit with multiple cached actions"""
        # Setup: Multiple cached steps
        mock_step.cached_steps = json.dumps([
            {"type": "click", "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 400}},
            {"type": "type", "text": "test@example.com", "bbox": {"x1": 150, "y1": 250, "x2": 350, "y2": 450}, "press_enter": False},
            {"type": "navigate", "url": "https://example.com/dashboard"}
        ])
        mock_execute.return_value = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify execute_cached_steps called with all steps
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0]
        parsed_steps = call_args[1]
        
        assert len(parsed_steps) == 3
        assert parsed_steps[0]["type"] == "click"
        assert parsed_steps[1]["type"] == "type"
        assert parsed_steps[2]["type"] == "navigate"
        
        # Verify cache result returned
        assert result.metadata.act_id == "cached"
        assert success is True


class TestCacheHitWithAdvancedClickTypes:
    """Test cache hit with advanced click types enabled"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_with_advanced_click_types_enabled(self, mock_execute, mock_nova, mock_step):
        """Test cache hit works normally with advanced click types enabled"""
        # Setup: Enable advanced click types
        mock_step.enable_advanced_click_types = True
        mock_execute.return_value = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify cache execution succeeded
        assert result.metadata.act_id == "cached"
        assert success is True
        
        # Verify Nova Act not called (cache hit)
        mock_nova.act.assert_not_called()
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_execution_ignores_advanced_click_types_flag(self, mock_execute, mock_nova, mock_step):
        """Test cache execution ignores enable_advanced_click_types flag (Requirement 6.2)"""
        # Setup: Enable advanced click types
        mock_step.enable_advanced_click_types = True
        mock_execute.return_value = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify execute_cached_steps was called (cache path taken)
        mock_execute.assert_called_once()
        
        # Verify the cached steps passed to executor don't include click_base_prompt
        call_args = mock_execute.call_args[0]
        parsed_steps = call_args[1]
        
        # Verify it's the raw cached steps, not modified by advanced click types
        assert isinstance(parsed_steps, list)
        assert len(parsed_steps) == 1
        assert parsed_steps[0]["type"] == "click"
        
        # Verify Nova Act was NOT called (no instruction with click_base_prompt)
        mock_nova.act.assert_not_called()
        
        # Verify cache result returned (flag was ignored)
        assert result.metadata.act_id == "cached"


class TestCacheHitReturnSignature:
    """Test cache hit maintains consistent return signature"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_return_signature_is_tuple_of_three(self, mock_execute, mock_nova, mock_step):
        """Test return signature is (result, success, logs)"""
        # Setup
        mock_execute.return_value = None
        
        # Execute
        return_value = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify tuple of 3 elements
        assert isinstance(return_value, tuple)
        assert len(return_value) == 3
    
    @patch('navigation_step.execute_cached_steps')
    def test_return_signature_types(self, mock_execute, mock_nova, mock_step):
        """Test return signature types are (object, bool, str)"""
        # Setup
        mock_execute.return_value = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify types
        assert isinstance(result, SimpleNamespace)
        assert isinstance(success, bool)
        assert isinstance(logs, str)


class TestCacheHitWithDifferentStepTypes:
    """Test cache hit with different action types"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_with_click_action(self, mock_execute, mock_nova, mock_step):
        """Test cache hit with click action"""
        mock_step.cached_steps = json.dumps([
            {"type": "click", "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 400}}
        ])
        mock_execute.return_value = None
        
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        assert result.metadata.act_id == "cached"
        assert success is True
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_with_type_action(self, mock_execute, mock_nova, mock_step):
        """Test cache hit with type action"""
        mock_step.cached_steps = json.dumps([
            {"type": "type", "text": "test input", "bbox": {"x1": 150, "y1": 250, "x2": 350, "y2": 450}, "press_enter": False}
        ])
        mock_execute.return_value = None
        
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        assert result.metadata.act_id == "cached"
        assert success is True
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_with_navigate_action(self, mock_execute, mock_nova, mock_step):
        """Test cache hit with navigate action"""
        mock_step.cached_steps = json.dumps([
            {"type": "navigate", "url": "https://example.com"}
        ])
        mock_execute.return_value = None
        
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        assert result.metadata.act_id == "cached"
        assert success is True
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_with_hover_action(self, mock_execute, mock_nova, mock_step):
        """Test cache hit with hover action"""
        mock_step.cached_steps = json.dumps([
            {"type": "hover", "bbox": {"x1": 200, "y1": 300, "x2": 400, "y2": 500}}
        ])
        mock_execute.return_value = None
        
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        assert result.metadata.act_id == "cached"
        assert success is True
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_with_scroll_action(self, mock_execute, mock_nova, mock_step):
        """Test cache hit with scroll action"""
        mock_step.cached_steps = json.dumps([
            {"type": "scroll", "direction": "down", "amount": 500}
        ])
        mock_execute.return_value = None
        
        result, success, logs = execute_navigation_step(mock_nova, mock_step, True)
        
        assert result.metadata.act_id == "cached"
        assert success is True


class TestCacheHitNoMissLogs:
    """Test cache hit does not generate cache miss logs"""
    
    @patch('navigation_step.execute_cached_steps')
    def test_cache_hit_no_cache_miss_log(self, mock_execute, mock_nova, mock_step, caplog):
        """Test cache hit does not log 'Cache miss' message"""
        # Setup
        mock_execute.return_value = None
        
        # Capture all logs
        with caplog.at_level(logging.INFO):
            # Execute
            execute_navigation_step(mock_nova, mock_step, True)
        
        # Verify no cache miss log
        assert "Cache miss" not in caplog.text
        # Verify cache hit log present
        assert "Cache hit" in caplog.text
