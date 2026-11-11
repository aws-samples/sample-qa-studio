"""Which secrets a list of steps needs.

Template insert / apply and the JSON import copy ``secret`` steps into a use
case without their values.  The response tells the caller which keys still
need a value (``missingSecrets``); the UI / CLI then collect the values and
store them through ``POST /usecase/{id}/secrets`` — the only place secrets
are created.  Nothing is persisted for a secret until its value is set.
"""
from typing import Any, Dict, Iterable, List

SECRET_STEP_TYPE = 'secret'


def secret_keys_of_steps(steps: Iterable[Dict[str, Any]]) -> List[str]:
    """Distinct, non-empty ``secret_key`` values of ``secret`` steps, in step order."""
    keys: List[str] = []
    for step in steps:
        key = step.get('secret_key') if step.get('step_type') == SECRET_STEP_TYPE else None
        if key and key not in keys:
            keys.append(key)
    return keys
