"""Variable layering, merge and validation.

Precedence (lowest → highest): application ``APPLICATION#{id} / VARIABLES``
→ use case ``USECASE#{id} / USECASE_VARIABLES`` → CLI / suite overrides.
``load_effective_usecase_variables`` is the one loader for the first two
layers; ``get_usecase_variables``, ``execute_usecase`` and
``execute_test_suite`` all go through it so the editor, the CLI and the
execution snapshot see the same values. ``merge_variables`` applies the
override layer on top.
"""
import re
import json
from typing import Any, Callable, Dict, List, Optional

from boto3.dynamodb.types import TypeDeserializer

APPLICATION_VARIABLES_SK = 'VARIABLES'
USECASE_VARIABLES_SK = 'USECASE_VARIABLES'

#: ``read_item(pk, sk)`` → the plain (deserialised) item, or ``None`` when absent.
ItemReader = Callable[[str, str], Optional[Dict[str, Any]]]


def table_item_reader(table) -> ItemReader:
    """``ItemReader`` over a boto3 resource ``Table`` (plain Python values)."""
    def read_item(pk: str, sk: str) -> Optional[Dict[str, Any]]:
        return table.get_item(Key={'pk': pk, 'sk': sk}).get('Item')
    return read_item


def client_item_reader(client, table_name: str) -> ItemReader:
    """``ItemReader`` over the low-level client; typed attributes are deserialised."""
    deserializer = TypeDeserializer()

    def read_item(pk: str, sk: str) -> Optional[Dict[str, Any]]:
        response = client.get_item(TableName=table_name, Key={'pk': {'S': pk}, 'sk': {'S': sk}})
        item = response.get('Item')
        if item is None:
            return None
        return {name: deserializer.deserialize(value) for name, value in item.items()}
    return read_item


def variables_from_item(item: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    The ``variables`` attribute of a ``VARIABLES`` / ``USECASE_VARIABLES``
    record as an ordered ``{key: value}`` dict.

    Accepts the stored list of ``{key, value}`` rows (legacy capitalised
    ``Key`` / ``Value`` too) and the legacy ``{key: value}`` map; entries
    without a key are dropped. Stored order is kept.
    """
    raw = (item or {}).get('variables') or []
    if isinstance(raw, dict):
        return {str(key): '' if value is None else str(value) for key, value in raw.items()}
    variables: Dict[str, str] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        key = entry.get('key') or entry.get('Key', '')
        if not key:
            continue
        value = entry.get('value') or entry.get('Value', '')
        variables[key] = value
    return variables


def merge_layers(app_vars: Dict[str, str], usecase_vars: Dict[str, str]) -> List[Dict[str, str]]:
    """
    Effective rows of the application and use-case layers.

    Application rows first (sorted by key, only those the use case does not
    shadow), then the use-case rows in stored order; each row carries
    ``source``: ``"application"`` or ``"usecase"``. Pure.

    Example:
        >>> merge_layers({'zone': 'eu', 'base': 'app'}, {'base': 'uc'})
        [{'key': 'zone', 'value': 'eu', 'source': 'application'},
         {'key': 'base', 'value': 'uc', 'source': 'usecase'}]
    """
    rows = [
        {'key': key, 'value': app_vars[key], 'source': 'application'}
        for key in sorted(app_vars) if key not in usecase_vars
    ]
    rows.extend({'key': key, 'value': value, 'source': 'usecase'} for key, value in usecase_vars.items())
    return rows


def rows_to_dict(rows: List[Dict[str, str]]) -> Dict[str, str]:
    """``{key: value}`` of effective rows (``source`` dropped), order kept."""
    return {row['key']: row['value'] for row in rows}


def load_application_variables(read_item: ItemReader, application_id: Optional[str]) -> Dict[str, str]:
    """The application layer (one ``get_item``); ``{}`` without an application."""
    if not application_id:
        return {}
    return variables_from_item(read_item(f'APPLICATION#{application_id}', APPLICATION_VARIABLES_SK))


def load_usecase_variables(read_item: ItemReader, usecase_id: str) -> Dict[str, str]:
    """The use-case layer (one ``get_item``)."""
    return variables_from_item(read_item(f'USECASE#{usecase_id}', USECASE_VARIABLES_SK))


def load_effective_usecase_variables(
    read_item: ItemReader,
    usecase_id: str,
    application_id: Optional[str],
) -> List[Dict[str, str]]:
    """
    Effective variables of a use case: application layer + use-case layer.

    Two ``get_item`` calls (one when ``application_id`` is ``None`` — a
    legacy use case without an application resolves exactly as before, every
    row tagged ``source: "usecase"``). No scan, no query.

    Args:
        read_item: ``table_item_reader`` / ``client_item_reader``.
        usecase_id: Use case whose variables are resolved.
        application_id: Its application, or ``None``.

    Returns:
        ``[{key, value, source}]`` in ``merge_layers`` order.
    """
    app_vars = load_application_variables(read_item, application_id)
    usecase_vars = load_usecase_variables(read_item, usecase_id)
    return merge_layers(app_vars, usecase_vars)


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
