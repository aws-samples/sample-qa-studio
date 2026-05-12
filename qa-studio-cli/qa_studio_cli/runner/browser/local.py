"""Local browser provisioner — NovaAct's default behaviour.

Nothing to provision: NovaAct itself launches a local Chromium instance
when it receives ``starting_page`` without a CDP endpoint.  This
provisioner is a no-op that simply packages the starting URL.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict

from qa_studio_cli.runner.browser.handle import BrowserHandle


class LocalBrowserProvisioner:
    """Default provisioner. Hands NovaAct the starting URL and exits."""

    name: ClassVar[str] = "local"

    def provision(self, context: Dict[str, Any]) -> BrowserHandle:
        starting_url = context.get("starting_url") or ""
        nova_kwargs: Dict[str, Any] = {"starting_page": starting_url}
        return BrowserHandle(nova_kwargs=nova_kwargs, teardown=None)
