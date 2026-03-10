from dataclasses import dataclass
from typing import List, Optional, Dict

@dataclass
class KeyValuePair:
    key: str
    value: str

@dataclass
class Execution:
    pk: str
    sk: str
    status: str
    starting_url: str
    created_at: str
    completed_at: Optional[str]
    executing_at: Optional[str]
    trigger_type: Optional[str]
    session_id: Optional[str]
    region: str
    suite_execution_id: Optional[str] = None
    suite_id: Optional[str] = None
    enable_cache: bool = False

@dataclass
class ExecutionStep:
    pk: str
    sk: str
    step_id: str
    sort: int
    instruction: str
    artefact: str
    logs: List[str]
    created_at: str
    secret_key: str
    step_type: str
    validation_type: str
    validation_operator: str
    validation_value: str
    capture_variable: str
    value_type: str
    assertion_variable: str
    enable_advanced_click_types: bool = False
    cached_steps: Optional[str] = None
    cache_last_updated: Optional[str] = None

@dataclass
class ExecutionVariables:
    pk: str
    sk: str
    variables: List[KeyValuePair]
    runtime_variables: List[KeyValuePair]
    created_at: str

@dataclass
class ExecutionHeaders:
    pk: str
    sk: str
    headers: Dict[str, str]
    created_at: str
