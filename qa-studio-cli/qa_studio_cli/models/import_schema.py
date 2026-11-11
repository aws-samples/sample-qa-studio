"""Pydantic models for QA Studio export JSON validation (client-side).

Used by ``qa-studio tests import`` to validate JSON test files before
sending them to the cloud-side ``/import`` endpoint. The model must
enumerate every step type and every per-type field that we want
preserved through the round-trip — pydantic v2's default
``extra='ignore'`` would otherwise silently drop any field not
declared here.

Mirrors the runtime ``ExecutionStep`` field set on the worker side
(``web-app/worker/models.py``) and the lambdas' ``step_copy.COPYABLE_STEP_FIELDS``
(pinned by ``web-app/lambdas/endpoints/test_step_copy_parity.py``). When new
step types or new step fields ship to the runtime, this model must be
updated in lockstep or ``qa-studio tests import`` will reject (or worse,
silently strip) the new shape.
"""

import re
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, field_validator, model_validator

from qa_studio_cli.validation import repeat_only_field_errors, validate_repeat_step


# Active step types plus the deprecated 'url' (kept for back-compat
# imports of older test files). 'url' steps still execute correctly on
# the runtime; new tests should use 'browser' with browser_action='navigate'.
VALID_STEP_TYPES = [
    "navigation",
    "url",  # deprecated but still valid for back-compat imports
    "browser",
    "secret",
    "validation",
    "retrieve_value",
    "assertion",
    "download",
    "transform",
    "network_assertion",
    "repeat",  # data-driven loop; children nested under ``steps``
]


class ExportStep(BaseModel):
    """A single step in the export JSON.

    Optional fields are step-type-specific. The validator only enforces
    ``sort``, ``instruction``, and ``step_type``; per-type field
    requirements are checked at runtime by the worker / CLI runner — with
    one exception: ``repeat`` steps are shape-checked here (dataset rules,
    one nesting level) because a bad dataset is rejected by the server
    anyway and failing locally is friendlier.

    Repeat steps nest their children under ``steps``.  The flat shape
    (``id`` + ``parent_step_id``) produced by older tooling is accepted
    too; the server remaps the ids.
    """

    sort: int = Field(..., gt=0)
    instruction: str = Field(..., min_length=1)
    step_type: str

    # Repeat step (data-driven loop): an application dataset reference *or*
    # inline rows — never both (``validate_repeat_shape``).
    dataset_id: Optional[str] = None
    repeat_columns: Optional[list[str]] = None
    repeat_rows: Optional[list[list[str]]] = None
    steps: list["ExportStep"] = []
    # Flat-shape nesting (older tooling): ``id`` of the parent repeat.
    id: Optional[str] = None
    parent_step_id: Optional[str] = None

    # Common across multiple step types
    capture_variable: Optional[str] = None
    assertion_variable: Optional[str] = None
    enable_advanced_click_types: Optional[bool] = None

    # Validation / assertion fields
    validation_type: Optional[str] = None
    validation_operator: Optional[str] = None
    validation_value: Optional[str] = None

    # Secret step
    secret_key: Optional[str] = None

    # Retrieve_value step
    value_type: Optional[str] = None
    value_source: Optional[str] = None
    value_format: Optional[str] = None  # used when value_type='date'

    # Browser step
    browser_action: Optional[str] = None
    browser_args: Optional[str] = None  # JSON-encoded

    # Transform step
    transform_operation: Optional[str] = None
    transform_args: Optional[str] = None  # JSON-encoded

    # Network assertion step — request side
    network_url_pattern: Optional[str] = None
    network_method: Optional[str] = None
    network_request_body: Optional[str] = None
    network_body_match_type: Optional[str] = None
    network_mock_response: Optional[str] = None
    network_mock_passthrough: Optional[bool] = None
    network_timeout: Optional[int] = None

    # Network assertion step — response side
    network_response_body: Optional[str] = None
    network_response_body_match_type: Optional[str] = None
    network_response_status: Optional[int] = None

    # Legacy field, kept for back-compat with very old export files.
    value_step: Optional[str] = None

    @field_validator("step_type")
    @classmethod
    def validate_step_type(cls, v: str) -> str:
        if v not in VALID_STEP_TYPES:
            raise ValueError(
                f"must be one of: {', '.join(VALID_STEP_TYPES)}"
            )
        return v

    @model_validator(mode="after")
    def validate_repeat_shape(self) -> "ExportStep":
        if self.step_type == "repeat":
            _, errors = validate_repeat_step(self.model_dump(include={
                "parent_step_id", "dataset_id", "repeat_columns", "repeat_rows",
            }))
            if errors:
                raise ValueError("; ".join(errors))
            for child in self.steps:
                if child.step_type == "repeat" or child.steps:
                    raise ValueError("repeat steps support one level of nesting only")
        else:
            if self.steps:
                raise ValueError("only repeat steps may contain nested steps")
            errors = repeat_only_field_errors(self.model_dump(include={"dataset_id", "repeat_columns", "repeat_rows"}))
            if errors:
                raise ValueError("; ".join(errors))
        return self


#: ``step_type`` of a template placeholder.  Deliberately *not* in
#: ``VALID_STEP_TYPES``: it is not executable — ``POST /import`` replaces it
#: with the template's steps (server-side expansion, template linkage kept).
TEMPLATE_STEP_TYPE = "template"

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class TemplateRefStep(BaseModel):
    """``{sort, step_type: "template", template_id}`` — and nothing else.

    The template's steps take this slot at import time.  ``template_id`` is
    the template's UUID (``qa-studio templates list``); UUIDs are specific
    to one QA Studio environment.
    """

    model_config = ConfigDict(extra="forbid")

    sort: int = Field(..., gt=0)
    step_type: Literal["template"]
    template_id: str

    @field_validator("template_id")
    @classmethod
    def validate_template_id(cls, v: str) -> str:
        if not _UUID_RE.match(v or ""):
            raise ValueError("template_id must be a template UUID (see 'qa-studio templates list')")
        return v


def _step_discriminator(value: Any) -> str:
    """``"template"`` → placeholder; everything else → ``ExportStep`` (which
    still rejects unknown ``step_type`` values with its own validator)."""
    step_type = value.get("step_type") if isinstance(value, dict) else getattr(value, "step_type", None)
    return TEMPLATE_STEP_TYPE if step_type == TEMPLATE_STEP_TYPE else "step"


ImportStep = Annotated[
    Union[
        Annotated[TemplateRefStep, Tag(TEMPLATE_STEP_TYPE)],
        Annotated[ExportStep, Tag("step")],
    ],
    Discriminator(_step_discriminator),
]


class ExportSecret(BaseModel):
    """A secret entry in the export JSON."""

    key: str = Field(..., min_length=1)
    description: str = ""


class ExportHooks(BaseModel):
    """Hook scripts in the export JSON."""

    beforeScript: str = ""
    afterScript: str = ""


#: Allowed ``test_platform`` values. Mirrors ``platforms.VALID_TEST_PLATFORMS``
#: in the lambdas — keep both in sync when a platform is added.
VALID_TEST_PLATFORMS = ("web", "mobile", "electron")

#: Mobile-only usecase attributes; forbidden on electron usecases so a
#: copy-pasted mobile export cannot be mis-tagged as a desktop test.
#: ``bundle_id`` is deliberately absent: electron usecases may carry the
#: app's CFBundleIdentifier, which the runner checks against the launched
#: ``.app``.
MOBILE_ONLY_FIELDS = (
    "platform", "app_package", "app_activity",
    "device_arn", "device_farm_project_arn",
)


class ExportUsecase(BaseModel):
    """Usecase metadata in the export JSON."""

    name: str = Field(..., min_length=1)
    starting_url: str = ""
    tags: list[str] = []
    description: str = ""
    active: bool = False
    executing_region: str = ""
    model_id: str = ""
    # ``web`` (default) | ``mobile`` | ``electron``. Electron usecases are
    # launched by the CI runner via ``--app-path``; they need no
    # ``starting_url`` and carry no mobile fields except an optional
    # ``bundle_id`` (the .app's CFBundleIdentifier, verified at launch).
    test_platform: str = "web"
    # Mobile fields — only meaningful when ``test_platform == "mobile"``
    # (``bundle_id`` is shared with electron).
    platform: str = ""
    app_package: str = ""
    app_activity: str = ""
    bundle_id: str = ""
    device_arn: str = ""
    device_farm_project_arn: str = ""

    @field_validator("test_platform")
    @classmethod
    def validate_test_platform(cls, v: str) -> str:
        value = v or "web"
        if value not in VALID_TEST_PLATFORMS:
            raise ValueError(
                f"test_platform must be one of: {', '.join(VALID_TEST_PLATFORMS)}"
            )
        return value

    @model_validator(mode="after")
    def mobile_fields_only_for_mobile(self) -> "ExportUsecase":
        if self.test_platform == "electron":
            present = [f for f in MOBILE_ONLY_FIELDS if getattr(self, f)]
            if present:
                raise ValueError(
                    f"fields {', '.join(present)} are not allowed for electron usecases"
                )
        return self


class ExportPayload(BaseModel):
    """Top-level export JSON schema (exportVersion 1.0)."""

    exportVersion: str = Field(...)
    exportedAt: str = Field(..., min_length=1)
    usecase: ExportUsecase
    steps: list[ImportStep] = Field(..., min_length=1)
    variables: list[dict] = []
    secrets: list[ExportSecret] = []
    hooks: Optional[ExportHooks] = None

    @field_validator("exportVersion")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError('exportVersion must be "1.0"')
        return v

    def template_ids(self) -> list[str]:
        """Distinct ``template_id`` values of the placeholder steps, in file order."""
        ids: list[str] = []
        for step in self.steps:
            if isinstance(step, TemplateRefStep) and step.template_id not in ids:
                ids.append(step.template_id)
        return ids


class TemplateFileMetadata(BaseModel):
    """``template`` block of a template file."""

    name: str = Field(..., min_length=1)
    description: str = ""
    category: str = ""
    tags: list[str] = []


class TemplateFileVariable(BaseModel):
    key: str = Field(..., min_length=1)
    value: str = ""


#: Templates hold plain steps only — mirrors the server rule
#: (``repeat_validation.REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR``).
REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR = "repeat steps are not supported in templates"
#: Mirrors ``template_expansion.NESTED_TEMPLATE_ERROR`` on the server.
NESTED_TEMPLATE_ERROR = "templates cannot contain template steps"


class TemplateFilePayload(BaseModel):
    """Template file (``templateVersion: "1.0"``) for ``qa-studio templates create | update``.

    Steps reuse ``ExportStep`` — so a placeholder can never appear inside a
    template — and secrets are not declared: they are derived from the
    ``secret_key`` of ``secret`` steps.  Templates cannot contain repeats, so
    ``steps[].id`` unambiguously means the *template step id*.
    """

    templateVersion: str = Field(...)
    template: TemplateFileMetadata
    steps: list[ExportStep] = Field(..., min_length=1)
    variables: list[TemplateFileVariable] = []

    @field_validator("templateVersion")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError('templateVersion must be "1.0"')
        return v

    @field_validator("steps", mode="before")
    @classmethod
    def reject_placeholders(cls, v: Any) -> Any:
        if isinstance(v, list) and any(
            isinstance(s, dict) and s.get("step_type") == TEMPLATE_STEP_TYPE for s in v
        ):
            raise ValueError(NESTED_TEMPLATE_ERROR)
        return v

    @field_validator("steps")
    @classmethod
    def reject_repeat(cls, v: list[ExportStep]) -> list[ExportStep]:
        if any(s.step_type == "repeat" or s.parent_step_id for s in v):
            raise ValueError(REPEAT_NOT_SUPPORTED_IN_TEMPLATES_ERROR)
        return v

    @model_validator(mode="after")
    def reject_duplicate_step_ids(self) -> "TemplateFilePayload":
        """``steps[].id`` is the template step id (``templates export`` emits it,
        ``templates update`` matches on it); the same id twice is ambiguous."""
        seen: set[str] = set()
        for step in self.steps:
            if step.id is None:
                continue
            if step.id in seen:
                raise ValueError(f"steps: duplicate step id {step.id}")
            seen.add(step.id)
        return self

    def secret_keys(self) -> list[str]:
        """Distinct ``secret_key`` values of ``secret`` steps, in step order."""
        keys: list[str] = []
        for step in self.steps:
            if step.step_type == "secret" and step.secret_key and step.secret_key not in keys:
                keys.append(step.secret_key)
        return keys
