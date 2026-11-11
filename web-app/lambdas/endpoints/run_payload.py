"""Data shapes shared by the MicroVM launcher (Lambda) and the supervisor (VM).

The launcher serialises a :class:`RunPayload` into the ``runHookPayload``
string of ``RunMicrovm``; the supervisor parses it back out of the ``/run``
hook body.  Both sides import this module, so it stays dependency-light:
pydantic only — no boto3, no imports from the rest of the worker.

Split between payload and image env (see ``web-app/worker/README.md``):
per-execution values travel in the payload, stack-constant values are
image-level env vars read by the supervisor.
"""

from __future__ import annotations

import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

#: Hard limit of the ``runHookPayload`` string (``RunMicrovm`` model metadata).
RUN_HOOK_PAYLOAD_MAX_BYTES = 4096

#: ``maximumDurationInSeconds`` platform range (1 s .. 8 h).
MAX_DURATION_UPPER_BOUND_S = 28_800

RunMode = Literal["batch", "wizard"]


class PayloadTooLargeError(ValueError):
    """The serialised payload exceeds :data:`RUN_HOOK_PAYLOAD_MAX_BYTES`."""


class MobileConfig(BaseModel):
    """Mobile use-case fields the launcher copies from the use-case record.

    :meth:`to_env` reproduces what ``execute_usecase.py`` exports to the ECS
    container today: every non-empty field, upper-cased.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    test_platform: str = "mobile"
    platform: Optional[str] = None
    app_package: Optional[str] = None
    app_activity: Optional[str] = None
    bundle_id: Optional[str] = None
    app_binary_s3_path: Optional[str] = None
    app_arn: Optional[str] = None
    device_farm_project_arn: Optional[str] = None
    device_arn: Optional[str] = None

    def to_env(self) -> dict[str, str]:
        return {name.upper(): value for name, value in self.model_dump().items() if value}


class RunPayload(BaseModel):
    """Everything per-execution the supervisor needs to spawn the child."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: RunMode
    usecase_id: str = Field(min_length=1)
    #: Batch only: the pre-created execution record the runner attaches to.
    execution_id: Optional[str] = None
    #: Batch only: raw worker capability; exported as
    #: ``QA_STUDIO_EXECUTION_TOKEN={usecase_id}:{execution_id}:{token}``.
    #: ``SecretStr`` so ``repr``/``model_dump_json`` never show it.
    execution_token: Optional[SecretStr] = None
    #: Wizard only: the wizard session (its execution record is ``EXECUTION#{session_id}``).
    session_id: Optional[str] = None
    #: Executing region (the regional artefact bucket is derived from it by the launcher).
    region: str = Field(min_length=1)
    #: Regional artefact bucket, ``{S3_BUCKET_PREFIX}-{region}``.
    s3_bucket: str = Field(min_length=1)
    #: Optional override of the image-level ``USER_AGENT``.
    user_agent: Optional[str] = None
    #: The VM's ``maximumDurationInSeconds``; the supervisor's soft timeout is derived from it.
    max_duration_s: int = Field(ge=1, le=MAX_DURATION_UPPER_BOUND_S)
    mobile: Optional[MobileConfig] = None

    @model_validator(mode="after")
    def _check_mode_fields(self) -> "RunPayload":
        if self.mode == "batch":
            missing = [name for name in ("execution_id", "execution_token") if getattr(self, name) is None]
            if missing:
                raise ValueError(f"batch mode requires {', '.join(missing)}")
        elif self.session_id is None:
            raise ValueError("wizard mode requires session_id")
        return self

    @property
    def run_id(self) -> str:
        """The identifier the child's execution record lives under."""
        run_id = self.execution_id if self.mode == "batch" else self.session_id
        if run_id is None:  # unreachable after validation; explicit for type narrowing
            raise ValueError(f"{self.mode} payload has no run identifier")
        return run_id

    def to_hook_payload(self) -> str:
        """Compact JSON for ``RunMicrovm(runHookPayload=...)``, token included."""
        data = self.model_dump(mode="json", exclude_none=True)
        if self.execution_token is not None:
            data["execution_token"] = self.execution_token.get_secret_value()
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True)
        _check_size(raw)
        return raw

    @classmethod
    def from_hook_payload(cls, raw: str) -> "RunPayload":
        """Parse the ``runHookPayload`` string; raises on size or shape errors."""
        _check_size(raw)
        return cls.model_validate_json(raw)


def _check_size(raw: str) -> None:
    size = len(raw.encode("utf-8"))
    if size > RUN_HOOK_PAYLOAD_MAX_BYTES:
        raise PayloadTooLargeError(
            f"runHookPayload is {size} bytes; the limit is {RUN_HOOK_PAYLOAD_MAX_BYTES} bytes"
        )
