"""
Pydantic models for browser recording data.

These models reflect the STRIPPED output from the NovaActRecorder Chrome extension.
Fields removed by the extension before transmission (rawAction, collapsedActions,
promptEdited, screenshotDataUrl, result) are NOT modeled here.

The recording data uses an extensible envelope pattern:
  - type="cdp_actions" for CDP-captured browser interactions (current)
  - Future types: "screenshot_sequence", "video"
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal


class Assertion(BaseModel):
    """User-defined expected outcome attached to an action (stripped)."""
    id: str
    text: str = Field(description="Natural language assertion")
    captureScreenshot: bool = False


class ActionEntry(BaseModel):
    """A single recorded action from the NovaActRecorder extension (stripped)."""
    id: str
    type: Literal[
        "click", "dblclick", "contextmenu", "type", "paste", "change",
        "pointer", "scroll", "navigation", "tab_switch", "intent", "extract_variable"
    ]
    prompt: str = Field(description="Generated or user-edited prompt text")
    url: str = Field(description="Page URL where action occurred")
    timestamp: int = Field(description="Capture time (ms since epoch)")
    isIntent: bool = False
    assertions: list[Assertion] = Field(default_factory=list)
    variableName: Optional[str] = None
    selectedText: Optional[str] = None
    sourceVariableName: Optional[str] = None


class RecordingSession(BaseModel):
    """A time-bounded sequence of actions captured by the NovaActRecorder extension."""
    id: str
    startedAt: int = Field(description="Timestamp ms since epoch")
    stoppedAt: Optional[int] = Field(default=None, description="Timestamp ms since epoch")
    tabId: int = Field(description="Chrome tab ID where recording started")
    startingUrl: str = Field(description="Initial page URL")
    name: Optional[str] = Field(default=None, description="User-assigned session name")
    actions: list[ActionEntry] = Field(description="Ordered action log")


class CDPRecordingPayload(BaseModel):
    """CDP action recording payload wrapping the extension's RecordingSession."""
    session: RecordingSession
    event_count: int = Field(description="Number of actions in the session")
    duration_seconds: Optional[float] = Field(
        default=None,
        description="Recording duration in seconds (computed from startedAt/stoppedAt)"
    )


class RecordingData(BaseModel):
    """
    Extensible recording envelope.

    Current types:
      - "cdp_actions": JSON of browser interactions captured via the NovaActRecorder extension

    Future types (not implemented yet):
      - "screenshot_sequence": Ordered screenshots with timestamps
      - "video": Browser session video recording
    """
    type: str = Field(description='Recording type: "cdp_actions", future: "screenshot_sequence", "video"')
    version: str = Field(default="1.0", description="Schema version for this type")
    data: dict = Field(description="Type-specific payload (CDPRecordingPayload for cdp_actions)")
    captured_at: str = Field(description="ISO8601 timestamp when recording was captured")
    screenshot_manifest_key: Optional[str] = Field(
        default=None,
        description="S3 key for screenshot manifest JSON ({actionId: s3Key})"
    )
    screenshot_s3_prefix: Optional[str] = Field(
        default=None,
        description="S3 prefix where screenshot JPEGs are stored"
    )


# --- API Request/Response Models ---

class RecordingCommandRequest(BaseModel):
    """Request body for POST /wizard/{sessionId}/command."""
    action: Literal["recording_start", "recording_stop"]


class RecordingDataResponse(BaseModel):
    """Response body for GET /wizard/{sessionId}/recording."""
    status: Literal["available", "not_available", "error"]
    recording_data: Optional[RecordingData] = None
    error: Optional[str] = None


class GenerateUsecaseRequest(BaseModel):
    """Request body for POST /generate-usecase (extended with optional recording data)."""
    title: str
    starting_url: str
    userJourney: str
    region: str
    recording_data: Optional[RecordingData] = None
