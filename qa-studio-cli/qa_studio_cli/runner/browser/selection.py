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
    """

    mode: BrowserMode = "local"
    cdp_endpoint_url: Optional[str] = None
    cdp_headers_file: Optional[str] = None

    @property
    def requires_agentcore_extra(self) -> bool:
        return self.mode == "agentcore"
