"""CDP-external browser provisioner.

Attaches to a CDP (Chrome DevTools Protocol) browser that someone else
has already provisioned. The runner receives the endpoint URL and any
required headers (for auth, session routing, etc.) and hands them to
NovaAct verbatim.

Typical users:

- The cloud worker wrapper, once AgentCore browser provisioning is
  separated out: the wrapper creates the browser, writes headers to a
  tempfile, invokes ``qa-studio run --browser cdp-external ...``.
- Advanced local setups where the developer runs their own remote
  browser and just wants to aim the CLI at it.

Headers MUST be delivered via a file path, not a CLI argument, so they
do not leak into ``ps``/process tables.  The CLI enforces this in its
flag definitions; the provisioner here accepts them already-parsed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

from qa_studio_cli.runner.browser.handle import BrowserHandle


class CdpExternalBrowserProvisioner:
    """Use an already-provisioned CDP browser.

    Parameters are provided at construction time (from CLI flags) rather
    than via ``context`` so that strategy selection can happen up-front.
    """

    name: ClassVar[str] = "cdp-external"

    def __init__(
        self,
        cdp_endpoint_url: str,
        cdp_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        if not cdp_endpoint_url:
            raise ValueError("cdp_endpoint_url is required for cdp-external browser mode")
        self._cdp_endpoint_url = cdp_endpoint_url
        self._cdp_headers = dict(cdp_headers or {})

    def provision(self, context: Dict[str, Any]) -> BrowserHandle:
        starting_url = context.get("starting_url") or ""
        nova_kwargs: Dict[str, Any] = {
            "cdp_endpoint_url": self._cdp_endpoint_url,
            "cdp_headers": self._cdp_headers,
            "starting_page": starting_url,
        }
        # We did not create the browser, so we do not destroy it.
        return BrowserHandle(nova_kwargs=nova_kwargs, teardown=None)

    # ------------------------------------------------------------------
    # Helpers for the CLI wiring
    # ------------------------------------------------------------------

    @classmethod
    def from_flags(
        cls,
        cdp_endpoint_url: str,
        cdp_headers_file: Optional[str],
    ) -> "CdpExternalBrowserProvisioner":
        """Build a provisioner from the two CLI flags.

        ``cdp_headers_file`` points at a JSON object on disk
        (``{"x-header": "value", ...}``).  Passing headers via file
        avoids leaking secrets through argv.
        """
        headers: Dict[str, str] = {}
        if cdp_headers_file:
            path = Path(cdp_headers_file)
            if not path.is_file():
                raise ValueError(f"cdp_headers_file not found: {cdp_headers_file}")
            try:
                loaded = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                raise ValueError(f"cdp_headers_file is not valid JSON: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ValueError("cdp_headers_file must contain a JSON object")
            # Coerce all keys and values to str — headers are string-typed
            headers = {str(k): str(v) for k, v in loaded.items()}
        return cls(cdp_endpoint_url=cdp_endpoint_url, cdp_headers=headers)
