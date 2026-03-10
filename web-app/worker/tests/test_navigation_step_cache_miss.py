"""Unit tests for navigation_step cache miss logging (Task 1.4)"""
import pytest
import json
import logging
from unittest.mock import Mock
from types import SimpleNamespace
from navigation_step import execute_navigation_step
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
    """Create mock ExecutionStep"""
    step = Mock(spec=ExecutionStep)
    step.sort = 1
    step.instruction = "Click login button"
    step.enable_advanced_click_types = False
    return step


class TestCacheMissLogging:
    """Test cache miss scenarios log appropriate INFO messages"""
    
    def test_cache_disabled_logs_info(self, mock_nova, mock_step, caplog):
        """Test cache miss logged when enable_cache=False"""
        # Setup: Cache disabled
        mock_step.enable_cache = False
        mock_step.cached_steps = json.dumps([{"type": "click", "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 400}}])
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            result, success, logs = execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify INFO log with correct message
        assert "Cache miss for step 1: caching disabled" in caplog.text
        
        # Verify Nova Act was called
        mock_nova.act.assert_called_once_with("Click login button")
        assert result.metadata.act_id == "nova_act_123"
    
    def test_no_cached_steps_logs_info(self, mock_nova, mock_step, caplog):
        """Test cache miss logged when cached_steps is None"""
        # Setup: Cache enabled but no cached steps
        mock_step.enable_cache = True
        mock_step.cached_steps = None
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            result, success, logs = execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify INFO log with correct message
        assert "Cache miss for step 1: no cached steps available" in caplog.text
        
        # Verify Nova Act was called
        mock_nova.act.assert_called_once_with("Click login button")
        assert result.metadata.act_id == "nova_act_123"
    
    def test_empty_cached_steps_logs_info(self, mock_nova, mock_step, caplog):
        """Test cache miss logged when cached_steps is empty string"""
        # Setup: Cache enabled but empty cached steps
        mock_step.enable_cache = True
        mock_step.cached_steps = ""
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            result, success, logs = execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify INFO log with correct message
        assert "Cache miss for step 1: no cached steps available" in caplog.text
        
        # Verify Nova Act was called
        mock_nova.act.assert_called_once_with("Click login button")
    
    def test_whitespace_cached_steps_logs_info(self, mock_nova, mock_step, caplog):
        """Test cache miss logged when cached_steps is only whitespace"""
        # Setup: Cache enabled but whitespace cached steps
        mock_step.enable_cache = True
        mock_step.cached_steps = "   \n\t  "
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            result, success, logs = execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify INFO log with correct message
        assert "Cache miss for step 1: no cached steps available" in caplog.text
        
        # Verify Nova Act was called
        mock_nova.act.assert_called_once_with("Click login button")
    
    def test_cache_disabled_takes_precedence(self, mock_nova, mock_step, caplog):
        """Test cache disabled message when both enable_cache=False and no cached_steps"""
        # Setup: Both conditions false
        mock_step.enable_cache = False
        mock_step.cached_steps = None
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            result, success, logs = execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify "caching disabled" message (takes precedence)
        assert "Cache miss for step 1: caching disabled" in caplog.text
        assert "no cached steps available" not in caplog.text


class TestCacheMissWithStepSort:
    """Test cache miss logs include correct step sort number"""
    
    def test_cache_miss_includes_step_sort(self, mock_nova, mock_step, caplog):
        """Test cache miss log includes step sort number"""
        # Setup: Different step sort
        mock_step.sort = 5
        mock_step.enable_cache = False
        mock_step.cached_steps = None
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify step sort in log message
        assert "Cache miss for step 5" in caplog.text
    
    def test_cache_miss_no_cached_steps_includes_sort(self, mock_nova, mock_step, caplog):
        """Test cache miss (no cached steps) log includes step sort number"""
        # Setup: Different step sort
        mock_step.sort = 10
        mock_step.enable_cache = True
        mock_step.cached_steps = None
        
        # Capture INFO level logs
        with caplog.at_level(logging.INFO):
            # Execute
            execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify step sort in log message
        assert "Cache miss for step 10" in caplog.text


class TestCacheMissDoesNotAffectExecution:
    """Test cache miss scenarios execute normally via Nova Act"""
    
    def test_cache_disabled_executes_via_nova_act(self, mock_nova, mock_step):
        """Test cache disabled executes step via Nova Act"""
        mock_step.enable_cache = False
        mock_step.cached_steps = json.dumps([{"type": "click", "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 400}}])
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify Nova Act called and result returned
        mock_nova.act.assert_called_once()
        assert result.metadata.act_id == "nova_act_123"
        assert success is True
        assert logs == ""
    
    def test_no_cached_steps_executes_via_nova_act(self, mock_nova, mock_step):
        """Test no cached steps executes step via Nova Act"""
        mock_step.enable_cache = True
        mock_step.cached_steps = None
        
        # Execute
        result, success, logs = execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify Nova Act called and result returned
        mock_nova.act.assert_called_once()
        assert result.metadata.act_id == "nova_act_123"
        assert success is True
        assert logs == ""
    
    def test_cache_miss_with_advanced_click_types(self, mock_nova, mock_step):
        """Test cache miss with advanced click types includes prompt"""
        mock_step.enable_cache = False
        mock_step.cached_steps = None
        mock_step.enable_advanced_click_types = True
        
        # Execute
        execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify instruction includes click_base_prompt
        call_args = mock_nova.act.call_args[0][0]
        assert "agentClick" in call_args
        assert "clickType" in call_args
        assert "Click login button" in call_args


class TestNoLogWhenCacheHit:
    """Test cache miss logs are not generated on cache hit"""
    
    def test_cache_hit_no_miss_log(self, mock_nova, mock_step, caplog):
        """Test cache hit does not log cache miss message"""
        # Setup: Valid cache
        mock_step.enable_cache = True
        mock_step.cached_steps = json.dumps([{"type": "click", "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 400}}])
        
        # Mock execute_cached_steps to succeed
        from unittest.mock import patch
        with patch('navigation_step.execute_cached_steps'):
            # Capture INFO level logs
            with caplog.at_level(logging.INFO):
                # Execute
                execute_navigation_step(mock_nova, mock_step, mock_step.enable_cache)
        
        # Verify no cache miss log
        assert "Cache miss" not in caplog.text
        # Verify cache hit log present
        assert "Cache hit for step 1" in caplog.text
