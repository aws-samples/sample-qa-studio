"""Return type for BrowserProvisioner.provision()."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class BrowserHandle:
    """Connection parameters and lifecycle hooks for a provisioned browser.

    The runner feeds the values in :attr:`nova_kwargs` into ``NovaAct(**kwargs)``.
    For the local strategy this is just ``starting_page`` plus whatever
    common options the runner already configures.  For remote strategies it
    includes ``cdp_endpoint_url`` and ``cdp_headers``.

    :attr:`live_view_url` is populated by provisioners that expose a
    separate user-visible live view (AgentCore only today).  When set and
    live-view publishing is enabled on the run, the runner will publish
    it via the live-view API endpoint.

    :attr:`teardown` is invoked in a ``finally`` block once the NovaAct
    context exits.  It MUST tolerate being called after a partial
    provisioning failure — provisioners are responsible for catching
    their own exceptions during teardown.
    """

    nova_kwargs: Dict[str, Any] = field(default_factory=dict)
    live_view_url: Optional[str] = None
    teardown: Optional[Callable[[], None]] = None
    # Extra metadata provisioners may want to surface (e.g. AgentCore
    # browser id, session arn). Opaque to the runner; useful for logs.
    metadata: Dict[str, Any] = field(default_factory=dict)
