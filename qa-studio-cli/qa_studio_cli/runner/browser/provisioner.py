"""Protocol all browser provisioners implement."""

from __future__ import annotations

from typing import Any, Dict, Protocol

from qa_studio_cli.runner.browser.handle import BrowserHandle


class BrowserProvisioner(Protocol):
    """Provisioning contract shared by local/agentcore/cdp-external strategies.

    A provisioner owns everything outside NovaAct's life cycle — creating,
    starting, and (on teardown) destroying the underlying browser.  The
    runner never talks to AgentCore, Playwright, or CDP transports
    directly; it asks the provisioner for a :class:`BrowserHandle`,
    unpacks ``nova_kwargs`` into ``NovaAct(**kwargs)``, and on exit calls
    ``handle.teardown()``.

    Implementations MUST be side-effect free at import time and raise a
    clear error if their environment prerequisites are missing (e.g.
    ``bedrock_agentcore`` not installed for the AgentCore strategy).
    """

    name: str

    def provision(self, context: Dict[str, Any]) -> BrowserHandle:
        """Build the NovaAct kwargs and return a handle.

        ``context`` is a free-form dict of execution-scoped inputs:
        ``starting_url``, ``execution_id``, ``usecase_id``, ``region``,
        and anything provisioner-specific (e.g. AgentCore's VPC config
        or an externally supplied CDP URL).  Strategies pick the keys
        they care about and ignore the rest.
        """
        ...
