"""Bedrock AgentCore browser provisioner.

Provisions a remote browser via Amazon Bedrock AgentCore's control plane,
starts a session, and hands the runner a :class:`BrowserHandle` with the
CDP endpoint, headers, live-view URL, and a teardown closure that stops
the session and deletes the browser.

Ports ``web-app/worker/browser.py`` semantics (the cloud worker today)
onto the CLI's BrowserProvisioner protocol (R-BROWSER-2).  The worker's
direct usage can be removed once the CLI-unified-runner refactor is
complete and the worker entrypoint simply invokes ``qa-studio run``.

Ships as part of the ``[agentcore]`` install extra so the ``bedrock_agentcore``
dependency doesn't leak into the base CLI install.  Attempting to use
this provisioner without the extra installed raises a clear error.

Configuration (all read from env so local devs and cloud workers share
the same surface):

- ``BEDROCK_EXECUTION_ROLE`` — IAM role the browser assumes at runtime
  (required by Bedrock AgentCore).  Must be pre-created.
- ``AGENT_CORE_VPC`` — ``"true"`` to put the browser in a VPC.  When set,
  ``AC_VPC_ID``, ``AC_SUBNET_ID``, ``AC_SECURITY_GROUP_ID`` must also be
  set.  Defaults to PUBLIC network mode.
- ``S3_BUCKET`` — artifact bucket the session recordings land in.

The context dict passed to :meth:`provision` carries per-execution inputs:
``usecase_id``, ``execution_id``, ``region``, ``unique_id`` (5-char rand
to namespace the browser resource), and optional ``browser_policy_s3_path``
(enterprise browser policy).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, ClassVar, Dict, Optional, Tuple

from qa_studio_cli.runner.browser.handle import BrowserHandle

logger = logging.getLogger(__name__)

# Browser creation can take several minutes; matches the worker's limit.
_BROWSER_READY_TIMEOUT_S = 600
_BROWSER_READY_POLL_INTERVAL_S = 1


class AgentCoreNotInstalledError(RuntimeError):
    """Raised when the ``[agentcore]`` extra isn't installed but needed."""


class AgentCoreBrowserProvisioner:
    """Provision a remote browser via Amazon Bedrock AgentCore.

    The provisioner is idempotent only in the trivial sense — a fresh
    browser is created on every ``provision()`` call.  The returned
    :class:`BrowserHandle` carries a teardown closure that stops the
    session and deletes the browser so callers get cleanup-for-free
    when they run the handle through the runner's ``finally`` block.
    """

    name: ClassVar[str] = "agentcore"

    def __init__(self, artefact_bucket: Optional[str] = None) -> None:
        """``artefact_bucket`` overrides the ``S3_BUCKET`` env var.

        Production deploys set ``S3_BUCKET`` in the ECS task definition;
        developers running locally pass it explicitly when they need
        AgentCore.  If neither is available the provisioner raises on
        :meth:`provision` — not construction — so unit tests can still
        instantiate it freely.
        """
        self._artefact_bucket = artefact_bucket or os.getenv("S3_BUCKET")

    def provision(self, context: Dict[str, Any]) -> BrowserHandle:
        usecase_id = context.get("usecase_id") or ""
        execution_id = context.get("execution_id") or ""
        region = context.get("region") or os.getenv("AWS_REGION", "us-east-1")
        unique_id = context.get("unique_id") or ""
        starting_url = context.get("starting_url") or ""
        browser_policy_s3_path = context.get("browser_policy_s3_path")

        if not self._artefact_bucket:
            raise RuntimeError(
                "S3_BUCKET env var (or artefact_bucket=...) is required to "
                "provision an AgentCore browser — it owns the recording "
                "destination.",
            )
        if not execution_id:
            raise RuntimeError(
                "execution_id is required in the provisioner context; "
                "AgentCore tags the session for artifact lookup.",
            )

        # Delay the bedrock_agentcore import until the provisioner is
        # actually used — keeps the CLI importable without the extra.
        try:
            from bedrock_agentcore.tools.browser_client import BrowserClient
        except ImportError as exc:
            raise AgentCoreNotInstalledError(
                "bedrock_agentcore is not installed. "
                "Install with: pip install 'qa-studio[agentcore]'",
            ) from exc

        # Control plane + data plane clients come from different boto3
        # shapes. The control plane creates/deletes browsers; the data
        # plane (BrowserClient) starts sessions.
        cp_client = _create_control_plane_client(region)

        recording_prefix = f"{usecase_id}/{execution_id}/recording/"
        browser_config = _build_browser_config(
            unique_id=unique_id or execution_id,
            execution_id=execution_id,
            artefact_bucket=self._artefact_bucket,
            artefact_prefix=recording_prefix,
            browser_policy_s3_path=browser_policy_s3_path,
        )

        logger.info(
            "Creating AgentCore browser: name=%s network=%s",
            browser_config["name"],
            browser_config["networkConfiguration"]["networkMode"],
        )
        creation_start = time.time()
        response = cp_client.create_browser(**browser_config)
        browser_id = response["browserId"]
        logger.info("AgentCore browser created: %s", browser_id)

        # Wait until the browser leaves CREATING/PENDING.  Raises on
        # FAILED/DELETED/timeout so caller teardown is skipped.
        _wait_for_browser_ready(cp_client, browser_id, creation_start)

        # Start a session.  The BrowserClient object is the thing that
        # exposes CDP endpoint, headers, and the live-view URL.
        browser_session = BrowserClient(region)
        browser_session.start(identifier=browser_id, name=execution_id)
        ws_url, cdp_headers = browser_session.generate_ws_headers()
        try:
            live_view_url: Optional[str] = browser_session.generate_live_view_url()
        except Exception as exc:
            # Live view is non-critical — a provisioner that exposes CDP
            # correctly is still usable; just without the frontend widget.
            logger.warning("Failed to generate live-view URL: %s", exc)
            live_view_url = None

        nova_kwargs: Dict[str, Any] = {
            "cdp_endpoint_url": ws_url,
            "cdp_headers": cdp_headers,
            "starting_page": starting_url,
        }

        def _teardown() -> None:
            _safe_teardown(browser_session, cp_client, browser_id)

        return BrowserHandle(
            nova_kwargs=nova_kwargs,
            live_view_url=live_view_url,
            teardown=_teardown,
            metadata={"browser_id": browser_id, "region": region},
        )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _create_control_plane_client(region: str):
    """Build the bedrock-agentcore-control boto3 client.

    Uses the explicit regional endpoint the worker uses — Bedrock
    AgentCore doesn't yet follow the default resolver in all regions.
    """
    import boto3  # imported lazily so base CLI install doesn't require boto3

    return boto3.client(
        "bedrock-agentcore-control",
        region_name=region,
        endpoint_url=f"https://bedrock-agentcore-control.{region}.amazonaws.com",
    )


def _build_browser_config(
    *,
    unique_id: str,
    execution_id: str,
    artefact_bucket: str,
    artefact_prefix: str,
    browser_policy_s3_path: Optional[str],
) -> Dict[str, Any]:
    """Produce the create_browser request body.

    VPC vs PUBLIC network mode is driven by the ``AGENT_CORE_VPC`` env
    var.  When VPC is requested, ``AC_VPC_ID`` / ``AC_SUBNET_ID`` /
    ``AC_SECURITY_GROUP_ID`` are all required — missing any of them
    raises.  Mirrors ``web-app/worker/utils.py::validate_vpc_configuration``.
    """
    execution_role = os.getenv("BEDROCK_EXECUTION_ROLE")
    if not execution_role:
        raise RuntimeError(
            "BEDROCK_EXECUTION_ROLE env var is required to create an "
            "AgentCore browser.",
        )

    network_mode, vpc_config = _resolve_network_config()

    config: Dict[str, Any] = {
        "name": f"nova_act_qa_studio_{unique_id}",
        "description": f"{network_mode} browser for {execution_id}",
        "networkConfiguration": {"networkMode": network_mode},
        "executionRoleArn": execution_role,
        # clientToken makes retries idempotent.  A fresh UUID per call
        # matches the worker — we don't currently retry at this level.
        "clientToken": str(uuid.uuid4()),
        "recording": {
            "enabled": True,
            "s3Location": {
                "bucket": artefact_bucket,
                "prefix": artefact_prefix,
            },
        },
    }
    if vpc_config is not None:
        config["networkConfiguration"]["vpcConfig"] = vpc_config

    if browser_policy_s3_path:
        config["enterprisePolicies"] = [
            {
                "type": "MANAGED",
                "location": {
                    "s3": {
                        "bucket": artefact_bucket,
                        "prefix": browser_policy_s3_path,
                    },
                },
            },
        ]
    return config


def _resolve_network_config() -> Tuple[str, Optional[Dict[str, Any]]]:
    """Return ``(networkMode, vpcConfig)`` based on env vars.

    Raises when VPC mode is enabled but required inputs are missing.
    """
    if os.getenv("AGENT_CORE_VPC", "false").lower() != "true":
        return "PUBLIC", None
    vpc_id = os.getenv("AC_VPC_ID")
    subnet_id = os.getenv("AC_SUBNET_ID")
    security_group_id = os.getenv("AC_SECURITY_GROUP_ID")
    missing = [
        name
        for name, value in (
            ("AC_VPC_ID", vpc_id),
            ("AC_SUBNET_ID", subnet_id),
            ("AC_SECURITY_GROUP_ID", security_group_id),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "AGENT_CORE_VPC=true but the following env vars are missing: "
            + ", ".join(missing),
        )
    vpc_config = {
        "securityGroups": [security_group_id],
        "subnets": [subnet_id],
    }
    return "VPC", vpc_config


def _wait_for_browser_ready(cp_client, browser_id: str, start_time: float) -> None:
    """Poll until the browser is READY, or raise on terminal/timeout."""
    attempts = 0
    while True:
        elapsed = time.time() - start_time
        if elapsed > _BROWSER_READY_TIMEOUT_S:
            raise RuntimeError(
                f"AgentCore browser {browser_id} did not reach READY within "
                f"{_BROWSER_READY_TIMEOUT_S}s",
            )
        attempts += 1
        try:
            response = cp_client.get_browser(browserId=browser_id)
        except Exception as exc:
            # "does not exist" means creation failed silently — surface as
            # hard error so we don't poll forever.
            if "does not exist" in str(exc).lower():
                raise RuntimeError(
                    f"AgentCore browser {browser_id} not found during status check",
                ) from exc
            logger.warning(
                "Error checking AgentCore browser status (attempt %d): %s",
                attempts, exc,
            )
            time.sleep(_BROWSER_READY_POLL_INTERVAL_S)
            continue

        status = response.get("status", "UNKNOWN")
        logger.info(
            "AgentCore browser %s status=%s (elapsed %.1fs)",
            browser_id, status, elapsed,
        )
        if status == "READY":
            return
        if status in ("FAILED", "DELETED"):
            raise RuntimeError(
                f"AgentCore browser {browser_id} ended in terminal status: {status}",
            )
        # CREATING / PENDING / unknown — keep polling
        time.sleep(_BROWSER_READY_POLL_INTERVAL_S)


def _safe_teardown(browser_session, cp_client, browser_id: str) -> None:
    """Stop the session and delete the browser.  Errors are logged, not raised.

    Teardown is called from the engine's ``finally`` block where an
    exception would mask the original failure.  The underlying resources
    are short-lived enough that an orphan is cheaper than a confused
    traceback.
    """
    try:
        browser_session.stop()
    except Exception as exc:
        logger.warning("AgentCore browser session stop failed: %s", exc)
    try:
        cp_client.delete_browser(browserId=browser_id)
    except Exception as exc:
        logger.warning(
            "AgentCore browser delete failed (id=%s): %s", browser_id, exc,
        )
