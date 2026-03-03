"""Unit tests for cache_executor module"""
import pytest
from unittest.mock import Mock, patch, call
from cache_executor import (
    execute_cached_steps,
    execute_cached_step,
    CacheExecutionError,
    DEFAULT_ACTION_DELAY_MS
)


@pytest.fixture
def mock_nova():
    """Create mock NovaAct instance with page attribute"""
    nova = Mock()
    nova.page = Mock()
    nova.page.mouse = Mock()
    nova.page.keyboard = Mock()
    nova.page.evaluate = Mock()
    nova.page.goto = Mock()
    return nova


class TestExecuteClick:
    def test_execute_click_calculates_center(self, mock_nova):
        """Test click action calculates bbox center correctly"""
        step = {
            'type': 'click',
            'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}
        }
        
        execute_cached_step(mock_nova, step)
        
        mock_nova.page.mouse.click.assert_called_once_with(200.0, 300.0)
    
    def test_execute_click_with_float_coordinates(self, mock_nova):
        """Test click with non-integer bbox coordinates"""
        step = {
            'type': 'click',
            'bbox': {'x1': 100, 'y1': 200, 'x2': 301, 'y2': 401}
        }
        
        execute_cached_step(mock_nova, step)
        
        mock_nova.page.mouse.click.assert_called_once_with(200.5, 300.5)


class TestExecuteHover:
    def test_execute_hover_calculates_center(self, mock_nova):
        """Test hover action calculates bbox center correctly"""
        step = {
            'type': 'hover',
            'bbox': {'x1': 50, 'y1': 100, 'x2': 150, 'y2': 250}
        }
        
        execute_cached_step(mock_nova, step)
        
        mock_nova.page.mouse.move.assert_called_once_with(100.0, 175.0)


class TestExecuteType:
    @patch('cache_executor.time.sleep')
    def test_execute_type_clicks_then_types(self, mock_sleep, mock_nova):
        """Test type action clicks to focus then types text"""
        step = {
            'type': 'type',
            'text': 'admin',
            'bbox': {'x1': 300, 'y1': 400, 'x2': 500, 'y2': 450},
            'press_enter': False
        }
        
        execute_cached_step(mock_nova, step)
        
        # Verify click to focus
        mock_nova.page.mouse.click.assert_called_once_with(400.0, 425.0)
        
        # Verify delay between click and type
        mock_sleep.assert_called_once()
        
        # Verify typing
        mock_nova.page.keyboard.type.assert_called_once_with('admin')
        
        # Verify Enter not pressed
        mock_nova.page.keyboard.press.assert_not_called()
    
    @patch('cache_executor.time.sleep')
    def test_execute_type_with_enter(self, mock_sleep, mock_nova):
        """Test type action with press_enter flag"""
        step = {
            'type': 'type',
            'text': 'search query',
            'bbox': {'x1': 100, 'y1': 100, 'x2': 400, 'y2': 150},
            'press_enter': True
        }
        
        execute_cached_step(mock_nova, step)
        
        # Verify Enter is pressed
        mock_nova.page.keyboard.press.assert_called_once_with("Enter")
    
    @patch('cache_executor.time.sleep')
    @patch('cache_executor.os.getenv')
    def test_execute_type_respects_custom_delay(self, mock_getenv, mock_sleep, mock_nova):
        """Test type action uses custom delay from environment"""
        mock_getenv.return_value = '250'  # 250ms custom delay
        
        step = {
            'type': 'type',
            'text': 'test',
            'bbox': {'x1': 0, 'y1': 0, 'x2': 100, 'y2': 100},
            'press_enter': False
        }
        
        execute_cached_step(mock_nova, step)
        
        # Verify custom delay is used (250ms = 0.25s)
        mock_sleep.assert_called_once_with(0.25)


class TestExecuteScroll:
    def test_execute_scroll_down(self, mock_nova):
        """Test scroll down action"""
        step = {
            'type': 'scroll',
            'direction': 'down',
            'bbox': {'x1': 0, 'y1': 0, 'x2': 1920, 'y2': 1080},
            'value': 500
        }
        
        execute_cached_step(mock_nova, step)
        
        mock_nova.page.evaluate.assert_called_once_with("window.scrollBy(0, 500)")
    
    def test_execute_scroll_up(self, mock_nova):
        """Test scroll up action"""
        step = {
            'type': 'scroll',
            'direction': 'up',
            'bbox': {'x1': 0, 'y1': 0, 'x2': 1920, 'y2': 1080},
            'value': 300
        }
        
        execute_cached_step(mock_nova, step)
        
        mock_nova.page.evaluate.assert_called_once_with("window.scrollBy(0, -300)")
    
    def test_execute_scroll_left(self, mock_nova):
        """Test scroll left action"""
        step = {
            'type': 'scroll',
            'direction': 'left',
            'bbox': {'x1': 0, 'y1': 0, 'x2': 1920, 'y2': 1080},
            'value': 200
        }
        
        execute_cached_step(mock_nova, step)
        
        mock_nova.page.evaluate.assert_called_once_with("window.scrollBy(-200, 0)")
    
    def test_execute_scroll_right(self, mock_nova):
        """Test scroll right action"""
        step = {
            'type': 'scroll',
            'direction': 'right',
            'bbox': {'x1': 0, 'y1': 0, 'x2': 1920, 'y2': 1080},
            'value': 400
        }
        
        execute_cached_step(mock_nova, step)
        
        mock_nova.page.evaluate.assert_called_once_with("window.scrollBy(400, 0)")
    
    def test_execute_scroll_default_amount(self, mock_nova):
        """Test scroll uses default amount when value not specified"""
        step = {
            'type': 'scroll',
            'direction': 'down',
            'bbox': {'x1': 0, 'y1': 0, 'x2': 1920, 'y2': 1080},
            'value': None
        }
        
        execute_cached_step(mock_nova, step)
        
        # Should use default 800px
        mock_nova.page.evaluate.assert_called_once_with("window.scrollBy(0, 800)")
    
    def test_execute_scroll_invalid_direction(self, mock_nova):
        """Test scroll raises error for invalid direction"""
        step = {
            'type': 'scroll',
            'direction': 'diagonal',
            'bbox': {'x1': 0, 'y1': 0, 'x2': 1920, 'y2': 1080},
            'value': 100
        }
        
        with pytest.raises(CacheExecutionError, match="Unknown scroll direction"):
            execute_cached_step(mock_nova, step)


class TestExecuteNavigate:
    def test_execute_navigate(self, mock_nova):
        """Test navigate action"""
        step = {
            'type': 'navigate',
            'url': 'https://example.com/login'
        }
        
        execute_cached_step(mock_nova, step)
        
        mock_nova.page.goto.assert_called_once_with('https://example.com/login')


class TestExecuteCachedSteps:
    @patch('cache_executor.time.sleep')
    def test_execute_multiple_steps_in_sequence(self, mock_sleep, mock_nova):
        """Test executing multiple cached steps in sequence"""
        cached_steps = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}},
            {'type': 'hover', 'bbox': {'x1': 50, 'y1': 100, 'x2': 150, 'y2': 250}},
            {'type': 'navigate', 'url': 'https://example.com'}
        ]
        
        execute_cached_steps(mock_nova, cached_steps)
        
        # Verify all actions executed
        assert mock_nova.page.mouse.click.call_count == 1
        assert mock_nova.page.mouse.move.call_count == 1
        assert mock_nova.page.goto.call_count == 1
        
        # Verify delays between steps (2 delays for 3 steps)
        assert mock_sleep.call_count == 2
    
    @patch('cache_executor.time.sleep')
    def test_execute_steps_no_delay_after_last(self, mock_sleep, mock_nova):
        """Test no delay after last step"""
        cached_steps = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}
        ]
        
        execute_cached_steps(mock_nova, cached_steps)
        
        # No delay for single step
        mock_sleep.assert_not_called()
    
    @patch('cache_executor.time.sleep')
    @patch('cache_executor.os.getenv')
    def test_execute_steps_custom_delay(self, mock_getenv, mock_sleep, mock_nova):
        """Test custom delay between steps"""
        mock_getenv.return_value = '200'  # 200ms
        
        cached_steps = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}},
            {'type': 'hover', 'bbox': {'x1': 50, 'y1': 100, 'x2': 150, 'y2': 250}}
        ]
        
        execute_cached_steps(mock_nova, cached_steps)
        
        # Verify custom delay used (200ms = 0.2s)
        mock_sleep.assert_called_once_with(0.2)
    
    def test_execute_steps_raises_on_failure(self, mock_nova):
        """Test execution raises CacheExecutionError on failure"""
        mock_nova.page.mouse.click.side_effect = Exception("Click failed")
        
        cached_steps = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}
        ]
        
        with pytest.raises(CacheExecutionError, match="Cache execution failed at step 1"):
            execute_cached_steps(mock_nova, cached_steps)
    
    def test_execute_steps_stops_on_first_failure(self, mock_nova):
        """Test execution stops at first failure"""
        mock_nova.page.mouse.click.side_effect = Exception("Click failed")
        
        cached_steps = [
            {'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}},
            {'type': 'hover', 'bbox': {'x1': 50, 'y1': 100, 'x2': 150, 'y2': 250}}
        ]
        
        with pytest.raises(CacheExecutionError):
            execute_cached_steps(mock_nova, cached_steps)
        
        # Verify second step never executed
        mock_nova.page.mouse.move.assert_not_called()


class TestUnknownActionType:
    def test_unknown_action_raises_error(self, mock_nova):
        """Test unknown action type raises CacheExecutionError"""
        step = {
            'type': 'unknown_action',
            'data': 'test'
        }
        
        with pytest.raises(CacheExecutionError, match="Unknown action type"):
            execute_cached_step(mock_nova, step)


class TestErrorHandling:
    def test_playwright_error_wrapped_in_cache_error(self, mock_nova):
        """Test Playwright errors are wrapped in CacheExecutionError"""
        mock_nova.page.mouse.click.side_effect = RuntimeError("Playwright error")
        
        step = {
            'type': 'click',
            'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}
        }
        
        with pytest.raises(CacheExecutionError, match="Failed to execute click"):
            execute_cached_step(mock_nova, step)
