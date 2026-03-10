"""Variable merge and validation utilities for test suite execution."""
import re
import json
from typing import Dict, Any, List


def merge_variables(
    secrets: Dict[str, str],
    usecase_vars: Dict[str, str],
    cli_vars: Dict[str, str]
) -> Dict[str, str]:
    """
    Merge variables with precedence: CLI > usecase > secrets.
    
    Implementation:
    1. Start with secrets (lowest priority)
    2. Override with usecase variables
    3. Override with CLI variables (highest priority)
    
    Args:
        secrets: Variables from Secrets Manager
        usecase_vars: Variables from usecase definition
        cli_vars: Variables from CLI arguments
    
    Returns:
        Merged dictionary
    
    Example:
        >>> merge_variables(
        ...     {'username': 'secret_user', 'password': 'secret_pass'},
        ...     {'username': 'usecase_user'},
        ...     {'username': 'cli_user'}
        ... )
        {'username': 'cli_user', 'password': 'secret_pass'}
    """
    merged = {}
    merged.update(secrets)
    merged.update(usecase_vars)
    merged.update(cli_vars)
    return merged


def validate_variables_resolved(
    usecase: Dict[str, Any],
    variables: Dict[str, str]
) -> None:
    """
    Verify all {{variable}} placeholders are resolved.
    
    Implementation:
    1. Convert usecase to JSON string
    2. Find all {{variable}} patterns using regex
    3. Check if each variable exists in variables dict
    4. Raise ValueError if any missing
    
    Args:
        usecase: Usecase definition (dict)
        variables: Merged variables dictionary
    
    Raises:
        ValueError: If unresolved variables found
    
    Example:
        >>> usecase = {'starting_url': 'https://example.com/{{env}}'}
        >>> variables = {'env': 'prod'}
        >>> validate_variables_resolved(usecase, variables)
        # No error
        
        >>> variables = {}
        >>> validate_variables_resolved(usecase, variables)
        ValueError: Unresolved variables: env
    """
    template_pattern = r'\{\{(\w+)\}\}'
    usecase_str = json.dumps(usecase)
    
    # Find all template variables
    found_vars = re.findall(template_pattern, usecase_str)
    
    # Check which ones are missing
    missing = [var for var in found_vars if var not in variables]
    
    if missing:
        raise ValueError(f"Unresolved variables: {', '.join(missing)}")


def get_unresolved_variables(usecase: Dict[str, Any]) -> List[str]:
    """
    Extract all {{variable}} placeholders from usecase definition.
    
    Helper function for testing and debugging.
    
    Args:
        usecase: Usecase definition
    
    Returns:
        List of variable names found in templates
    """
    template_pattern = r'\{\{(\w+)\}\}'
    usecase_str = json.dumps(usecase)
    return re.findall(template_pattern, usecase_str)
