"""Security tests for the CLI browser step — RFC1918 / metadata IP blocking.

Mirrors web-app/worker/tests/test_security.py so the CLI enforces the same
network-guard the cloud worker does. See requirement R-PARITY-1 in
.kiro/specs/cli-unified-runner/requirements.md.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import pytest


# step_executor imports nova_act at module level, which is part of the
# [runner] extra and not installed in base test envs. Stub it so the
# module imports cleanly.
sys.modules.setdefault("nova_act", type(sys)("nova_act"))
_nova_act_mod = sys.modules["nova_act"]
if not hasattr(_nova_act_mod, "NovaAct"):
    _nova_act_mod.NovaAct = type("NovaAct", (), {})
if not hasattr(_nova_act_mod, "BOOL_SCHEMA"):
    _nova_act_mod.BOOL_SCHEMA = {"type": "boolean"}
if not hasattr(_nova_act_mod, "Workflow"):
    _nova_act_mod.Workflow = type("Workflow", (), {})

from qa_studio_cli.runner.step_executor import (  # noqa: E402
    StepExecutor,
    _validate_navigate_url,
)


# ---------------------------------------------------------------------------
# Validator unit tests — directly exercise the helper
# ---------------------------------------------------------------------------


class TestValidateNavigateUrl:
    def test_http_public_dns_passes(self):
        assert _validate_navigate_url("http://example.com/") is None

    def test_https_public_dns_passes(self):
        assert _validate_navigate_url("https://example.com/path?q=1") is None

    def test_non_http_scheme_rejected(self):
        error = _validate_navigate_url("file:///etc/passwd")
        assert error is not None
        assert "scheme" in error.lower()

    def test_empty_hostname_rejected(self):
        error = _validate_navigate_url("http:///path")
        assert error is not None
        assert "hostname" in error.lower()

    def test_metadata_ipv4_blocked(self):
        error = _validate_navigate_url("http://169.254.169.254/latest/meta-data/")
        assert error is not None
        assert "blocked" in error.lower()

    def test_metadata_ipv6_ula_blocked(self):
        error = _validate_navigate_url("http://[fd00::1]/")
        assert error is not None

    def test_ipv6_loopback_blocked(self):
        error = _validate_navigate_url("http://[::1]/admin")
        assert error is not None

    def test_ipv6_link_local_blocked(self):
        error = _validate_navigate_url("http://[fe80::1]/")
        assert error is not None

    def test_loopback_blocked(self):
        error = _validate_navigate_url("http://127.0.0.1/admin")
        assert error is not None

    def test_rfc1918_10_blocked(self):
        error = _validate_navigate_url("http://10.0.0.1/internal")
        assert error is not None

    def test_rfc1918_172_16_blocked(self):
        error = _validate_navigate_url("http://172.16.0.1/")
        assert error is not None

    def test_rfc1918_172_31_blocked(self):
        # Upper edge of the 172.16/12 range
        error = _validate_navigate_url("http://172.31.255.255/")
        assert error is not None

    def test_rfc1918_192_168_blocked(self):
        error = _validate_navigate_url("http://192.168.1.1/")
        assert error is not None

    def test_public_ipv4_allowed(self):
        assert _validate_navigate_url("http://8.8.8.8/") is None

    def test_public_ipv6_allowed(self):
        # Cloudflare IPv6
        assert _validate_navigate_url("http://[2606:4700:4700::1111]/") is None

    def test_dns_name_not_resolved(self):
        # We don't do DNS resolution; a DNS name that would resolve to an
        # internal IP still passes. The guard is strictly about literal IPs.
        # Documents the current behaviour.
        assert _validate_navigate_url("http://internal.example.com/") is None


# ---------------------------------------------------------------------------
# Integration tests — through StepExecutor._execute_browser
# ---------------------------------------------------------------------------


def _make_nova():
    nova = MagicMock()
    nova.page = MagicMock()
    nova.page.url = "https://example.com"
    return nova


def _navigate_step(url: str) -> dict:
    return {
        "step_type": "browser",
        "browser_action": "navigate",
        "browser_args": json.dumps({"url": url}),
    }


class TestBrowserStepNavigateGuard:
    def test_navigate_to_metadata_is_blocked(self):
        nova = _make_nova()
        executor = StepExecutor(nova)
        result = executor.execute(_navigate_step("http://169.254.169.254/"), {}, {})
        assert result.success is False
        assert "blocked" in result.logs.lower()
        nova.go_to_url.assert_not_called()

    def test_navigate_to_rfc1918_is_blocked(self):
        nova = _make_nova()
        executor = StepExecutor(nova)
        result = executor.execute(_navigate_step("http://10.1.2.3/"), {}, {})
        assert result.success is False
        assert "blocked" in result.logs.lower()
        nova.go_to_url.assert_not_called()

    def test_navigate_to_loopback_is_blocked(self):
        nova = _make_nova()
        executor = StepExecutor(nova)
        result = executor.execute(_navigate_step("http://127.0.0.1:8080/"), {}, {})
        assert result.success is False
        nova.go_to_url.assert_not_called()

    def test_navigate_rejects_non_http_scheme(self):
        nova = _make_nova()
        executor = StepExecutor(nova)
        result = executor.execute(_navigate_step("file:///etc/passwd"), {}, {})
        assert result.success is False
        assert "scheme" in result.logs.lower()
        nova.go_to_url.assert_not_called()

    def test_navigate_to_public_url_passes_through(self):
        nova = _make_nova()
        executor = StepExecutor(nova)
        result = executor.execute(_navigate_step("https://example.com/"), {}, {})
        assert result.success is True
        nova.go_to_url.assert_called_once_with("https://example.com/")

    def test_navigate_requires_url(self):
        nova = _make_nova()
        executor = StepExecutor(nova)
        step = {
            "step_type": "browser",
            "browser_action": "navigate",
            "browser_args": json.dumps({}),
        }
        result = executor.execute(step, {}, {})
        assert result.success is False
        assert "url" in result.logs.lower()
        nova.go_to_url.assert_not_called()
