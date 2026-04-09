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
    test_platform: Optional[str] = None
    platform: Optional[str] = None
    app_identifier: Optional[str] = None
    app_binary_s3_path: Optional[str] = None
    app_arn: Optional[str] = None
    device_farm_project_arn: Optional[str] = None
    device_arn: Optional[str] = None
    device_farm_session_arn: Optional[str] = None
    device_name: Optional[str] = None
    device_os_version: Optional[str] = None
    browser_policy_s3_path: Optional[str] = None

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
    value_source: str = ''
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


from pydantic import BaseModel


class MobileAppConfig(BaseModel):
    platform: str  # "ANDROID" or "IOS"
    app_package: Optional[str] = None  # Android only
    app_activity: Optional[str] = None  # Android only
    bundle_id: Optional[str] = None  # iOS only
    app_binary_path: Optional[str] = None  # Local path to downloaded binary
    app_arn: Optional[str] = None  # Device Farm app ARN
    device_farm_project_arn: Optional[str] = None
    device_arn: Optional[str] = None
