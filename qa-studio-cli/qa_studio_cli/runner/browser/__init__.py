"""Browser provisioning strategies for the QA Studio runner.

The runner has to work across three browser provisioning shapes:

- **local**  — the CLI spins up a local browser directly (developer runs,
  CI runs today, default everywhere).
- **agentcore** — a remote Bedrock AgentCore browser is provisioned
  before the run and the CLI connects via CDP.  Used by the cloud worker;
  ships via the ``[agentcore]`` install extra (R-BROWSER-2).
- **cdp-external** — the CLI attaches to an already-provisioned browser
  via ``--cdp-endpoint-url`` + ``--cdp-headers-file``.  Used by advanced
  integrations and by the worker wrapper once AgentCore provisioning is
  separate.

Each strategy implements :class:`BrowserProvisioner` and returns a
:class:`BrowserHandle` describing the NovaAct connection parameters and
any cleanup callable.

See ``.kiro/specs/cli-unified-runner/design.md`` for the design rationale
and the migration plan that introduces the non-local strategies.
"""

from qa_studio_cli.runner.browser.cdp_external import CdpExternalBrowserProvisioner
from qa_studio_cli.runner.browser.handle import BrowserHandle
from qa_studio_cli.runner.browser.local import LocalBrowserProvisioner
from qa_studio_cli.runner.browser.provisioner import BrowserProvisioner
from qa_studio_cli.runner.browser.selection import BrowserSelection

__all__ = [
    "BrowserHandle",
    "BrowserProvisioner",
    "BrowserSelection",
    "CdpExternalBrowserProvisioner",
    "LocalBrowserProvisioner",
]


def _agentcore_provisioner_cls():
    """Lazy accessor for ``AgentCoreBrowserProvisioner``.

    Returns the class — import is deferred so the base CLI (without the
    ``[agentcore]`` extra) can still load this package.  The
    ``bedrock_agentcore`` dependency only materialises when an AgentCore
    provisioner is actually instantiated.  Raises
    :class:`AgentCoreNotInstalledError` on use when the extra is missing.
    """
    from qa_studio_cli.runner.browser.agentcore import (
        AgentCoreBrowserProvisioner,
        AgentCoreNotInstalledError,  # noqa: F401 — re-exported for tests
    )

    return AgentCoreBrowserProvisioner
