"""
DynamoDB schema utilities for Test Suites feature.

This module provides schema definitions and helper functions for managing
test suite entities in DynamoDB following the single-table design pattern.

Schema Entities:
- Test Suite: pk='TEST_SUITES', sk='SUITE#{suite_id}'
- Suite-UseCase Mapping: pk='SUITE#{suite_id}', sk='USECASE#{usecase_id}'
- Suite Execution: pk='SUITE_EXECUTION#{suite_id}', sk='EXECUTION#{suite_execution_id}'
- Suite Execution Result: pk='SUITE_EXEC#{suite_execution_id}', sk='RESULT#{usecase_id}'
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


# ============================================================================
# Partition Key (pk) and Sort Key (sk) Generation Functions
# ============================================================================

def get_test_suites_pk() -> str:
    """
    Get partition key for listing all test suites.
    
    Returns:
        'TEST_SUITES'
    """
    return 'TEST_SUITES'


def get_suite_sk(suite_id: str) -> str:
    """
    Get sort key for a specific test suite.
    
    Args:
        suite_id: UUID of the test suite
        
    Returns:
        'SUITE#{suite_id}'
    """
    return f'SUITE#{suite_id}'


def get_suite_mapping_pk(suite_id: str) -> str:
    """
    Get partition key for suite-usecase mappings.
    
    Args:
        suite_id: UUID of the test suite
        
    Returns:
        'SUITE#{suite_id}'
    """
    return f'SUITE#{suite_id}'


def get_usecase_mapping_sk(usecase_id: str) -> str:
    """
    Get sort key for a specific usecase mapping.
    
    Args:
        usecase_id: UUID of the use case
        
    Returns:
        'USECASE#{usecase_id}'
    """
    return f'USECASE#{usecase_id}'


def get_suite_execution_pk(suite_id: str) -> str:
    """
    Get partition key for suite executions.
    
    Args:
        suite_id: UUID of the test suite
        
    Returns:
        'SUITE_EXECUTION#{suite_id}'
    """
    return f'SUITE_EXECUTION#{suite_id}'


def get_execution_sk(suite_execution_id: str) -> str:
    """
    Get sort key for a specific suite execution.
    
    Args:
        suite_execution_id: UUID of the suite execution
        
    Returns:
        'EXECUTION#{suite_execution_id}'
    """
    return f'EXECUTION#{suite_execution_id}'


def get_suite_exec_result_pk(suite_execution_id: str) -> str:
    """
    Get partition key for suite execution results.
    
    Args:
        suite_execution_id: UUID of the suite execution
        
    Returns:
        'SUITE_EXEC#{suite_execution_id}'
    """
    return f'SUITE_EXEC#{suite_execution_id}'


def get_result_sk(usecase_id: str) -> str:
    """
    Get sort key for a specific execution result.
    
    Args:
        usecase_id: UUID of the use case
        
    Returns:
        'RESULT#{usecase_id}'
    """
    return f'RESULT#{usecase_id}'


# ============================================================================
# Entity Creation Functions
# ============================================================================

def create_test_suite_item(
    suite_id: str,
    name: str,
    description: str,
    scope: str,
    tags: List[str],
    created_by: str,
    created_at: str,
    schedule_enabled: bool = False,
    schedule_expression: Optional[str] = None,
    schedule_timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a test suite DynamoDB item.
    
    Args:
        suite_id: UUID for the test suite
        name: Suite name
        description: Suite description
        scope: OAuth scope for the suite (e.g., 'suite:smoke-tests')
        tags: List of tags
        created_by: User ID who created the suite
        created_at: ISO 8601 timestamp
        schedule_enabled: Whether scheduling is enabled
        schedule_expression: Cron expression for scheduling
        schedule_timezone: Timezone for scheduling
        
    Returns:
        DynamoDB item dictionary
    """
    item = {
        'pk': get_test_suites_pk(),
        'sk': get_suite_sk(suite_id),
        'id': suite_id,
        'name': name,
        'description': description,
        'scope': scope,
        'tags': tags,
        'created_at': created_at,
        'updated_at': created_at,
        'created_by': created_by,
        'schedule_enabled': schedule_enabled,
        'total_usecases': 0
    }
    
    # Add optional schedule fields
    if schedule_expression:
        item['schedule_expression'] = schedule_expression
    if schedule_timezone:
        item['schedule_timezone'] = schedule_timezone
    
    return item


def create_suite_usecase_mapping_item(
    suite_id: str,
    usecase_id: str,
    usecase_name: str,
    usecase_scope: str,
    added_by: str,
    added_at: str
) -> Dict[str, Any]:
    """
    Create a suite-usecase mapping DynamoDB item.
    
    Args:
        suite_id: UUID of the test suite
        usecase_id: UUID of the use case
        usecase_name: Name of the use case (denormalized)
        usecase_scope: Scope of the use case (denormalized)
        added_by: User ID who added the mapping
        added_at: ISO 8601 timestamp
        
    Returns:
        DynamoDB item dictionary
    """
    return {
        'pk': get_suite_mapping_pk(suite_id),
        'sk': get_usecase_mapping_sk(usecase_id),
        'suite_id': suite_id,
        'usecase_id': usecase_id,
        'usecase_name': usecase_name,
        'usecase_scope': usecase_scope,
        'added_by': added_by,
        'added_at': added_at
    }


def create_suite_execution_item(
    suite_execution_id: str,
    suite_id: str,
    suite_name: str,
    suite_scope: str,
    triggered_by: str,
    trigger_type: str,
    total_usecases: int,
    started_at: str,
    status: str = 'pending'
) -> Dict[str, Any]:
    """
    Create a suite execution DynamoDB item.
    
    Args:
        suite_execution_id: UUID for the suite execution
        suite_id: UUID of the test suite
        suite_name: Name of the suite (denormalized)
        suite_scope: Scope of the suite (denormalized)
        triggered_by: User ID who triggered the execution
        trigger_type: 'manual' or 'scheduled'
        total_usecases: Total number of use cases in the suite
        started_at: ISO 8601 timestamp
        status: Execution status (default: 'pending')
        
    Returns:
        DynamoDB item dictionary
    """
    return {
        'pk': get_suite_execution_pk(suite_id),
        'sk': get_execution_sk(suite_execution_id),
        'id': suite_execution_id,
        'suite_id': suite_id,
        'suite_name': suite_name,
        'suite_scope': suite_scope,
        'status': status,
        'started_at': started_at,
        'triggered_by': triggered_by,
        'trigger_type': trigger_type,
        'total_usecases': total_usecases,
        'completed_usecases': 0,
        'successful_usecases': 0,
        'failed_usecases': 0,
        'running_usecases': total_usecases  # Initialize to total since all start as running
    }


def create_suite_execution_result_item(
    suite_execution_id: str,
    usecase_id: str,
    usecase_name: str,
    status: str = 'pending'
) -> Dict[str, Any]:
    """
    Create a suite execution result DynamoDB item.
    
    Args:
        suite_execution_id: UUID of the suite execution
        usecase_id: UUID of the use case
        usecase_name: Name of the use case (denormalized)
        status: Result status (default: 'pending')
        
    Returns:
        DynamoDB item dictionary
    """
    return {
        'pk': get_suite_exec_result_pk(suite_execution_id),
        'sk': get_result_sk(usecase_id),
        'suite_execution_id': suite_execution_id,
        'usecase_id': usecase_id,
        'usecase_name': usecase_name,
        'status': status
    }


# ============================================================================
# Update Helper Functions
# ============================================================================

def get_suite_update_expression(
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    updated_at: Optional[str] = None,
    schedule_enabled: Optional[bool] = None,
    schedule_expression: Optional[str] = None,
    schedule_timezone: Optional[str] = None,
    last_execution_id: Optional[str] = None,
    last_execution_status: Optional[str] = None,
    last_execution_time: Optional[str] = None,
    last_successful_count: Optional[int] = None,
    total_usecases: Optional[int] = None
) -> tuple[str, Dict[str, Any]]:
    """
    Build DynamoDB update expression for test suite updates.
    
    Args:
        name: New suite name
        description: New description
        tags: New tags list
        updated_at: New timestamp
        schedule_enabled: Schedule enabled flag
        schedule_expression: Cron expression
        schedule_timezone: Timezone
        last_execution_id: Last execution ID
        last_execution_status: Last execution status
        last_execution_time: Last execution time
        last_successful_count: Last successful count
        total_usecases: Total use cases count
        
    Returns:
        Tuple of (update_expression, expression_attribute_values, expression_attribute_names)
    """
    update_parts = []
    expression_values = {}
    expression_names = {}
    
    if name is not None:
        # 'name' is a DynamoDB reserved keyword — must use an alias
        update_parts.append('#n = :name')
        expression_names['#n'] = 'name'
        expression_values[':name'] = name
    
    if description is not None:
        update_parts.append('description = :description')
        expression_values[':description'] = description
    
    if tags is not None:
        update_parts.append('tags = :tags')
        expression_values[':tags'] = tags
    
    if updated_at is not None:
        update_parts.append('updated_at = :updated_at')
        expression_values[':updated_at'] = updated_at
    
    if schedule_enabled is not None:
        update_parts.append('schedule_enabled = :schedule_enabled')
        expression_values[':schedule_enabled'] = schedule_enabled
    
    if schedule_expression is not None:
        update_parts.append('schedule_expression = :schedule_expression')
        expression_values[':schedule_expression'] = schedule_expression
    
    if schedule_timezone is not None:
        update_parts.append('schedule_timezone = :schedule_timezone')
        expression_values[':schedule_timezone'] = schedule_timezone
    
    if last_execution_id is not None:
        update_parts.append('last_execution_id = :last_execution_id')
        expression_values[':last_execution_id'] = last_execution_id
    
    if last_execution_status is not None:
        update_parts.append('last_execution_status = :last_execution_status')
        expression_values[':last_execution_status'] = last_execution_status
    
    if last_execution_time is not None:
        update_parts.append('last_execution_time = :last_execution_time')
        expression_values[':last_execution_time'] = last_execution_time
    
    if last_successful_count is not None:
        update_parts.append('last_successful_count = :last_successful_count')
        expression_values[':last_successful_count'] = last_successful_count
    
    if total_usecases is not None:
        update_parts.append('total_usecases = :total_usecases')
        expression_values[':total_usecases'] = total_usecases
    
    update_expression = 'SET ' + ', '.join(update_parts) if update_parts else ''
    
    return update_expression, expression_values, expression_names


def get_suite_execution_counter_update(
    status_change: str
) -> tuple[str, Dict[str, Any]]:
    """
    Build DynamoDB update expression for suite execution counter updates.
    
    This function handles atomic counter updates when use case execution
    status changes (e.g., from 'running' to 'completed').
    
    Args:
        status_change: Status transition, one of:
            - 'start': pending -> running
            - 'success': running -> completed (success)
            - 'failure': running -> failed
            
    Returns:
        Tuple of (update_expression, expression_attribute_values)
    """
    if status_change == 'start':
        # Increment running, decrement pending (if tracked)
        return (
            'ADD running_usecases :inc',
            {':inc': 1}
        )
    elif status_change == 'success':
        # Increment completed and successful, decrement running
        return (
            'ADD completed_usecases :inc, successful_usecases :inc, running_usecases :dec',
            {':inc': 1, ':dec': -1}
        )
    elif status_change == 'failure':
        # Increment completed and failed, decrement running
        return (
            'ADD completed_usecases :inc, failed_usecases :inc, running_usecases :dec',
            {':inc': 1, ':dec': -1}
        )
    else:
        raise ValueError(f'Invalid status_change: {status_change}')


# ============================================================================
# Query Helper Functions
# ============================================================================

def parse_suite_id_from_sk(sk: str) -> str:
    """
    Extract suite ID from sort key.
    
    Args:
        sk: Sort key in format 'SUITE#{suite_id}'
        
    Returns:
        Suite ID
    """
    return sk.replace('SUITE#', '')


def parse_usecase_id_from_sk(sk: str) -> str:
    """
    Extract usecase ID from sort key.
    
    Args:
        sk: Sort key in format 'USECASE#{usecase_id}' or 'RESULT#{usecase_id}'
        
    Returns:
        Usecase ID
    """
    if sk.startswith('USECASE#'):
        return sk.replace('USECASE#', '')
    elif sk.startswith('RESULT#'):
        return sk.replace('RESULT#', '')
    else:
        raise ValueError(f'Invalid sort key format: {sk}')


def parse_execution_id_from_sk(sk: str) -> str:
    """
    Extract execution ID from sort key.
    
    Args:
        sk: Sort key in format 'EXECUTION#{execution_id}'
        
    Returns:
        Execution ID
    """
    return sk.replace('EXECUTION#', '')
