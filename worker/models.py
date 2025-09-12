from dataclasses import dataclass
from typing import List, Optional


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
    headless: bool
    created_at: str
    completed_at: Optional[str] = None
    executing_at: Optional[str] = None
    trigger_type: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class ExecutionStep:
    pk: str
    sk: str
    step_id: str
    sort: int
    instruction: str
    step_type: str = "navigation"  # "navigation", "secret", "validation", "retrieve_value", or "assertion"
    secret_key: str = ""
    validation_type: str = ""  # "bool" or "string"
    validation_operator: str = ""  # "exact" or "contains"
    validation_value: str = ""  # Expected value for validation
    artefact: str = ""
    logs: List[str] = None
    created_at: str = ""
    capture_variable: str = ""  # Optional: custom name for runtime variable capture
    value_type: str = ""  # For retrieve_value steps: "string", "number", "bool"
    assertion_variable: str = ""  # For assertion steps: name of runtime variable to compare
    
    def __post_init__(self):
        if self.logs is None:
            self.logs = []


@dataclass
class ExecutionVariables:
    pk: str
    sk: str
    variables: List[KeyValuePair]
    created_at: str
    runtime_variables: Optional[List[KeyValuePair]] = None
    
    def __post_init__(self):
        if self.runtime_variables is None:
            self.runtime_variables = []