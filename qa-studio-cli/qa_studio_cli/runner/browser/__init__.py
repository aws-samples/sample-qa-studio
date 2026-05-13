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
from qa_studio_cli.runner.browser.local import (
    LOCAL_BROWSER_OPTIONS,
    LocalBrowserOption,
    LocalBrowserProvisioner,
    list_local_browsers,
)
from qa_studio_cli.runner.browser.provisioner import BrowserProvisioner
from qa_studio_cli.runner.browser.selection import BrowserSelection

__all__ = [
    "BrowserHandle",
    "BrowserProvisioner",
    "BrowserSelection",
    "CdpExternalBrowserProvisioner",
    "LOCAL_BROWSER_OPTIONS",
    "LocalBrowserOption",
    "LocalBrowserProvisioner",
    "list_local_browsers",
    "record_video_supported",
]


def record_video_supported(nova_kwargs: "dict[str, object]") -> bool:
    """Return whether ``record_video=True`` is compatible with these kwargs.

    NovaAct's Playwright backend raises ``ValidationFailed`` with the
    message *"Cannot record video when connecting over CDP"* whenever
    the kwargs imply a CDP connection — either to a remote browser
    (``cdp_endpoint_url`` set) or to the user's installed Chrome
    (``use_default_chrome_browser=True``). Both apply across our
    browser modes:

    * ``cdp-external`` / ``agentcore`` — sets ``cdp_endpoint_url``.
    * ``local`` with ``local_browser="chrome-profile"`` — sets
      ``use_default_chrome_browser=True``.

    Mobile executions pass an ``actuator`` and go through Appium,
    which supports video recording via Device Farm independently of
    this Playwright rule; mobile kwargs do not set either flag so
    they are (correctly) reported as supported.

    Centralised here so every caller reasons about NovaAct's rule the
    same way — do not reimplement this predicate at the call sites.
    """
    if nova_kwargs.get("cdp_endpoint_url"):
        return False
    if nova_kwargs.get("use_default_chrome_browser"):
        return False
    return True


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
