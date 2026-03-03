"""
Parse Nova Act responses into cacheable step format.

This module extracts cacheable actions (click, hover, scroll, type, navigate)
from Nova Act rawProgramBody responses and converts them to structured format
for cache storage and replay.
"""

import re
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


def parse_nova_act_steps(act_response: dict) -> Optional[List[Dict]]:
    """
    Parse Nova Act response into cacheable steps.
    
    Args:
        act_response: Nova Act response dict with 'steps' array
        
    Returns:
        List of cacheable step dicts, or None if no cacheable actions found
        
    Example:
        >>> response = {'steps': [{'response': {'rawProgramBody': 'agentClick("<box>100,200,300,400</box>");'}}]}
        >>> parse_nova_act_steps(response)
        [{'type': 'click', 'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400}}]
    """
    if not act_response or 'steps' not in act_response:
        logger.warning("Invalid act_response: missing 'steps' field")
        return None
    
    cached_steps = []
    
    for step_idx, step in enumerate(act_response.get('steps', [])):
        if 'response' not in step or 'rawProgramBody' not in step['response']:
            logger.warning(f"Step {step_idx}: missing rawProgramBody, skipping")
            continue
            
        raw_body = step['response']['rawProgramBody']
        
        # Parse each action type
        parsed = _parse_click(raw_body) or \
                 _parse_hover(raw_body) or \
                 _parse_type(raw_body) or \
                 _parse_scroll(raw_body) or \
                 _parse_navigate(raw_body)
        
        if parsed:
            cached_steps.append(parsed)
    
    return cached_steps if cached_steps else None


def _parse_click(raw_body: str) -> Optional[Dict]:
    """Parse agentClick action."""
    match = re.search(r'agentClick\("?<box>(\d+),(\d+),(\d+),(\d+)</box>"?\)', raw_body)
    if match:
        return {
            'type': 'click',
            'bbox': {
                'x1': int(match.group(1)),
                'y1': int(match.group(2)),
                'x2': int(match.group(3)),
                'y2': int(match.group(4))
            }
        }
    return None


def _parse_hover(raw_body: str) -> Optional[Dict]:
    """Parse agentHover action."""
    match = re.search(r'agentHover\("?<box>(\d+),(\d+),(\d+),(\d+)</box>"?\)', raw_body)
    if match:
        return {
            'type': 'hover',
            'bbox': {
                'x1': int(match.group(1)),
                'y1': int(match.group(2)),
                'x2': int(match.group(3)),
                'y2': int(match.group(4))
            }
        }
    return None


def _parse_type(raw_body: str) -> Optional[Dict]:
    """Parse agentType action."""
    # Match: agentType("text", "<box>x1,y1,x2,y2</box>", true/false)
    match = re.search(
        r'agentType\("([^"]*)",\s*"?<box>(\d+),(\d+),(\d+),(\d+)</box>"?(?:,\s*(true|false))?\)',
        raw_body
    )
    if match:
        return {
            'type': 'type',
            'text': match.group(1),
            'bbox': {
                'x1': int(match.group(2)),
                'y1': int(match.group(3)),
                'x2': int(match.group(4)),
                'y2': int(match.group(5))
            },
            'press_enter': match.group(6) == 'true' if match.group(6) else False
        }
    return None


def _parse_scroll(raw_body: str) -> Optional[Dict]:
    """Parse agentScroll action."""
    # Match: agentScroll("direction", "<box>x1,y1,x2,y2</box>", value?)
    match = re.search(
        r'agentScroll\("(up|down|left|right)",\s*"?<box>(\d+),(\d+),(\d+),(\d+)</box>"?(?:,\s*(\d+(?:\.\d+)?))?\)',
        raw_body
    )
    if match:
        return {
            'type': 'scroll',
            'direction': match.group(1),
            'bbox': {
                'x1': int(match.group(2)),
                'y1': int(match.group(3)),
                'x2': int(match.group(4)),
                'y2': int(match.group(5))
            },
            'value': float(match.group(6)) if match.group(6) else None
        }
    return None


def _parse_navigate(raw_body: str) -> Optional[Dict]:
    """Parse goToUrl action."""
    match = re.search(r'goToUrl\("([^"]+)"\)', raw_body)
    if match:
        return {
            'type': 'navigate',
            'url': match.group(1)
        }
    return None
