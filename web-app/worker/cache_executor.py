"""Execute cached Nova Act steps using Playwright API"""
import logging
import time
import os
from typing import List, Dict
from nova_act import NovaAct

logger = logging.getLogger(__name__)

# Configurable delay between actions (milliseconds)
# Override via CACHE_ACTION_DELAY_MS environment variable
DEFAULT_ACTION_DELAY_MS = 100


class CacheExecutionError(Exception):
    """Raised when cache execution fails"""
    pass


def execute_cached_steps(nova: NovaAct, cached_steps: List[Dict]):
    """
    Execute all cached steps in sequence.
    
    Args:
        nova: NovaAct instance with page attribute
        cached_steps: List of cached step dictionaries
        
    Raises:
        CacheExecutionError: If any step execution fails
    """
    delay_ms = int(os.getenv('CACHE_ACTION_DELAY_MS', DEFAULT_ACTION_DELAY_MS))
    delay_seconds = delay_ms / 1000.0
    
    for i, step in enumerate(cached_steps):
        try:
            logger.info(f"Executing cached step {i + 1}/{len(cached_steps)}: {step['type']}")
            execute_cached_step(nova, step)
            
            if i < len(cached_steps) - 1:  # Don't delay after last step
                time.sleep(delay_seconds)
                
        except Exception as e:
            logger.error(f"Failed to execute cached step {i + 1}: {step['type']} - {e}")
            raise CacheExecutionError(f"Cache execution failed at step {i + 1}: {e}") from e


def execute_cached_step(nova: NovaAct, step: Dict):
    """
    Execute a single cached step using Playwright API.
    
    Args:
        nova: NovaAct instance with page attribute
        step: Cached step dictionary with type and parameters
        
    Raises:
        CacheExecutionError: If step execution fails
    """
    action_type = step['type']
    
    try:
        if action_type == 'click':
            _execute_click(nova, step)
        elif action_type == 'hover':
            _execute_hover(nova, step)
        elif action_type == 'type':
            _execute_type(nova, step)
        elif action_type == 'scroll':
            _execute_scroll(nova, step)
        elif action_type == 'navigate':
            _execute_navigate(nova, step)
        else:
            raise CacheExecutionError(f"Unknown action type: {action_type}")
            
    except Exception as e:
        if isinstance(e, CacheExecutionError):
            raise
        raise CacheExecutionError(f"Failed to execute {action_type}: {e}") from e


def _execute_click(nova: NovaAct, step: Dict):
    """Execute click action at bbox center"""
    bbox = step['bbox']
    x = (bbox['x1'] + bbox['x2']) / 2.0
    y = (bbox['y1'] + bbox['y2']) / 2.0
    
    logger.info(f"Clicking at ({x}, {y})")
    nova.page.mouse.click(x, y)


def _execute_hover(nova: NovaAct, step: Dict):
    """Execute hover action at bbox center"""
    bbox = step['bbox']
    x = (bbox['x1'] + bbox['x2']) / 2.0
    y = (bbox['y1'] + bbox['y2']) / 2.0
    
    logger.info(f"Hovering at ({x}, {y})")
    nova.page.mouse.move(x, y)


def _execute_type(nova: NovaAct, step: Dict):
    """Execute type action - click to focus, then type text"""
    bbox = step['bbox']
    x = (bbox['x1'] + bbox['x2']) / 2.0
    y = (bbox['y1'] + bbox['y2']) / 2.0
    text = step['text']
    press_enter = step.get('press_enter', False)
    
    delay_ms = int(os.getenv('CACHE_ACTION_DELAY_MS', DEFAULT_ACTION_DELAY_MS))
    delay_seconds = delay_ms / 1000.0
    
    logger.info(f"Clicking at ({x}, {y}) to focus")
    nova.page.mouse.click(x, y)
    
    time.sleep(delay_seconds)
    
    logger.info(f"Typing text: {text[:50]}{'...' if len(text) > 50 else ''}")
    nova.page.keyboard.type(text)
    
    if press_enter:
        logger.info("Pressing Enter")
        nova.page.keyboard.press("Enter")


def _execute_scroll(nova: NovaAct, step: Dict):
    """Execute scroll action in specified direction"""
    direction = step['direction']
    amount = step.get('value')
    
    # If no amount specified, use default from Nova Act instruction
    if amount is None:
        amount = 800  # Default fallback
    
    logger.info(f"Scrolling {direction} by {amount}px")
    
    if direction == 'down':
        nova.page.evaluate(f"window.scrollBy(0, {amount})")
    elif direction == 'up':
        nova.page.evaluate(f"window.scrollBy(0, -{amount})")
    elif direction == 'left':
        nova.page.evaluate(f"window.scrollBy(-{amount}, 0)")
    elif direction == 'right':
        nova.page.evaluate(f"window.scrollBy({amount}, 0)")
    else:
        raise CacheExecutionError(f"Unknown scroll direction: {direction}")


def _execute_navigate(nova: NovaAct, step: Dict):
    """Execute navigation to URL"""
    url = step['url']
    logger.info(f"Navigating to: {url}")
    nova.page.goto(url)
