"""Variable merge utilities."""

from typing import Dict


def merge_variables(api_variables: Dict[str, str], cli_overrides: Dict[str, str]) -> Dict[str, str]:
    """Merge API variables with CLI overrides. CLI overrides take precedence."""
    return {**api_variables, **cli_overrides}
