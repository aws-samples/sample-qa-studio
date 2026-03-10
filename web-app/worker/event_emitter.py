"""
Event emission module for worker execution completion events.

This module provides functionality to emit EventBridge events after test execution
completes. Events are emitted using a fire-and-forget pattern where failures are
logged but do not affect test execution outcomes.
"""

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def emit_execution_completed_event(
    usecase_id: str,
    execution_id: str,
    execution_status: str,
    region_name: Optional[str] = None
) -> None:
    """
    Emit a usecase.execution.completed event to EventBridge.
    
    This function follows a fire-and-forget pattern: all exceptions are caught
    and logged, but never raised to the caller. This ensures that event emission
    failures do not impact test execution.
    
    Args:
        usecase_id: The usecase identifier
        execution_id: The execution identifier
        execution_status: Final execution status ("success" or "failed")
        region_name: AWS region (optional, uses boto3 default if not provided)
    
    Returns:
        None
    
    Example:
        >>> emit_execution_completed_event("uc_123", "exec_456", "success", "us-east-1")
    """
    try:
        # Initialize EventBridge client
        import boto3
        
        try:
            if region_name:
                eventbridge = boto3.client('events', region_name=region_name)
            else:
                eventbridge = boto3.client('events')
        except Exception as client_error:
            logger.error(f"Failed to initialize EventBridge client: {client_error}")
            return
        
        # Create event detail
        timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        event_detail = {
            'usecase_id': usecase_id,
            'execution_id': execution_id,
            'execution_status': execution_status,
            'timestamp': timestamp
        }
        
        # Log event detail at DEBUG level
        logger.debug(f"Event detail: {json.dumps(event_detail)}")
        
        # Create event entry
        event_entry = {
            'Source': 'qa-studio.worker',
            'DetailType': 'usecase.execution.completed',
            'Detail': json.dumps(event_detail)
        }
        
        # Emit event to EventBridge
        try:
            eventbridge.put_events(Entries=[event_entry])
            logger.info(
                f"Emitted execution completed event: {usecase_id}/{execution_id} -> {execution_status}"
            )
        except Exception as emission_error:
            logger.error(f"Failed to emit execution completed event: {emission_error}")
            return
            
    except Exception as unexpected_error:
        # Catch any unexpected errors to ensure fire-and-forget behavior
        logger.error(f"Unexpected error in emit_execution_completed_event: {unexpected_error}")
        return
