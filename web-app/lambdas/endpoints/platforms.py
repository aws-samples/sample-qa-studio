"""Shared ``test_platform`` vocabulary for the usecase lambdas.

One place for the allowed values and the two user-facing error strings so
create / update / import / execute / execute_test_suite never drift
(the frontend tooltip reuses ``ELECTRON_CI_RUNNER_ONLY_ERROR`` verbatim).

Platforms:
- ``web``      — browser test; runs locally, in CI, or in the cloud worker.
- ``mobile``   — Device Farm; needs ``platform`` + app identifiers.
- ``electron`` — desktop app launched by the CI runner (``qa-studio run
  --app-path …``). The cloud worker has no display, so every trigger
  other than ``ci_runner`` is refused.
"""

from typing import Optional

from utils import create_response

VALID_TEST_PLATFORMS = ("web", "mobile", "electron")

ELECTRON_CI_RUNNER_ONLY_ERROR = (
    "Electron usecases can only be executed by the CI runner (qa-studio run)"
)

#: The only trigger that may create an execution for an electron usecase.
ELECTRON_ALLOWED_TRIGGER = "ci_runner"


def validate_test_platform(value: Optional[str]) -> Optional[dict]:
    """Return a 400 response when ``value`` is not a known platform.

    Empty / missing means ``web`` (the historical default) and passes.
    """
    if not value:
        return None
    if value in VALID_TEST_PLATFORMS:
        return None
    return create_response(400, {
        "error": f"test_platform must be one of: {', '.join(VALID_TEST_PLATFORMS)}",
    })


def electron_trigger_allowed(test_platform: str, trigger_type: str) -> bool:
    """True unless an electron usecase is being launched by anything but the CI runner."""
    return test_platform != "electron" or trigger_type == ELECTRON_ALLOWED_TRIGGER
