"""Browser-selection DTO passed from CLI flags through to the engine.

A small dataclass avoids threading three loose strings through every
layer.  Construction helper ``from_flags`` validates combinations at the
call site so the engine can trust the invariants once it receives the
object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

BrowserMode = Literal["local", "agentcore", "cdp-external"]


@dataclass(frozen=True)
class BrowserSelection:
    """Captures the user's ``--browser`` choice + any CDP inputs.

    ``mode=local`` (default) and ``mode=cdp-external`` are valid on both
    local-only and remote paths.  ``mode=agentcore`` is only valid on
    the remote path — the engine enforces this.

    ``local_browser`` is only consulted when ``mode == "local"`` — it
    selects which flavour of the Chromium family NovaAct launches (see
    :data:`qa_studio_cli.runner.browser.local.LOCAL_BROWSER_OPTIONS`).
    CDP-external and AgentCore connect to a browser the caller or the
    cloud already provisioned and ignore this field.
    """

    mode: BrowserMode = "local"
    cdp_endpoint_url: Optional[str] = None
    cdp_headers_file: Optional[str] = None
    local_browser: str = "chromium"
    #: Explicit override for NovaAct's ``headless`` kwarg. ``None``
    #: defers to the engine's legacy ``HEADLESS`` env-var default so
    #: existing CI callers stay headless without changing anything.
    #: ``True`` forces headless, ``False`` forces headful (visible
    #: browser window).
    headless: Optional[bool] = None

    @property
    def requires_agentcore_extra(self) -> bool:
        return self.mode == "agentcore"
