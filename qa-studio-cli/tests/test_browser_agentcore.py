"""Tests for AgentCoreBrowserProvisioner (T2.6).

All AWS and AgentCore clients are mocked. The provisioner's contract
is exercised end-to-end: build the create_browser payload, poll until
READY, return a BrowserHandle with CDP + live-view + teardown.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub bedrock_agentcore before importing the provisioner.
# ---------------------------------------------------------------------------


def _install_agentcore_stubs():
    for name in (
        "bedrock_agentcore",
        "bedrock_agentcore.tools",
        "bedrock_agentcore.tools.browser_client",
    ):
        sys.modules.setdefault(name, ModuleType(name))

    bc_mod = sys.modules["bedrock_agentcore.tools.browser_client"]
    if not hasattr(bc_mod, "BrowserClient"):
        # Tests replace this with a MagicMock per-test; the default keeps
        # import-time collection working.
        bc_mod.BrowserClient = MagicMock()


_install_agentcore_stubs()


from qa_studio_cli.runner.browser import BrowserHandle  # noqa: E402
from qa_studio_cli.runner.browser.agentcore import (  # noqa: E402
    AgentCoreBrowserProvisioner,
    AgentCoreNotInstalledError,
    build_browser_config,
    parse_subnet_ids,
    resolve_network_config,
    _safe_teardown,
    _wait_for_browser_ready,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def env(monkeypatch):
    """Provide a minimal env setup the provisioner needs."""
    monkeypatch.setenv("BEDROCK_EXECUTION_ROLE", "arn:aws:iam::1:role/nova-act")
    monkeypatch.setenv("S3_BUCKET", "studio-artefacts")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("AGENT_CORE_VPC", raising=False)
    monkeypatch.delenv("AC_VPC_ID", raising=False)
    monkeypatch.delenv("AC_SUBNET_ID", raising=False)
    monkeypatch.delenv("AC_SUBNET_IDS", raising=False)
    monkeypatch.delenv("AC_SECURITY_GROUP_ID", raising=False)
    return monkeypatch


def _ready_response():
    return {"status": "READY"}


def _creating_response():
    return {"status": "CREATING"}


# ---------------------------------------------------------------------------
# resolve_network_config / parse_subnet_ids
# ---------------------------------------------------------------------------


def _set_vpc_env(env, subnets="subnet-1,subnet-2"):
    env.setenv("AGENT_CORE_VPC", "true")
    env.setenv("AC_VPC_ID", "vpc-1")
    env.setenv("AC_SUBNET_IDS", subnets)
    env.setenv("AC_SECURITY_GROUP_ID", "sg-1")


class TestParseSubnetIds:
    @pytest.mark.parametrize("raw, expected", [
        (None, []),
        ("", []),
        ("subnet-1", ["subnet-1"]),
        ("subnet-1,subnet-2", ["subnet-1", "subnet-2"]),
        (" subnet-2 , subnet-1 ,", ["subnet-2", "subnet-1"]),
        (",,", []),
    ])
    def test_split_strip_drop_empty(self, raw, expected):
        assert parse_subnet_ids(raw) == expected


class TestResolveNetworkConfig:
    def test_default_public(self, env):
        mode, vpc = resolve_network_config()
        assert mode == "PUBLIC"
        assert vpc is None

    @pytest.mark.parametrize("flag", ["false", "FALSE", "", "1", "yes"])
    def test_non_true_flag_is_public_even_with_ac_vars(self, env, flag):
        _set_vpc_env(env)
        env.setenv("AGENT_CORE_VPC", flag)
        assert resolve_network_config() == ("PUBLIC", None)

    def test_vpc_full_env_passes_every_subnet_in_order(self, env):
        _set_vpc_env(env, subnets="subnet-b, subnet-a,subnet-c")
        mode, vpc = resolve_network_config()
        assert mode == "VPC"
        assert vpc == {
            "securityGroups": ["sg-1"],
            "subnets": ["subnet-b", "subnet-a", "subnet-c"],
        }

    def test_flag_is_case_insensitive(self, env):
        _set_vpc_env(env)
        env.setenv("AGENT_CORE_VPC", "True")
        assert resolve_network_config()[0] == "VPC"

    def test_vpc_missing_fields_named(self, env):
        env.setenv("AGENT_CORE_VPC", "true")
        env.setenv("AC_VPC_ID", "vpc-1")
        with pytest.raises(RuntimeError) as exc:
            resolve_network_config()
        assert "AC_SUBNET_IDS" in str(exc.value)
        assert "AC_SECURITY_GROUP_ID" in str(exc.value)
        assert "AC_VPC_ID" not in str(exc.value)

    def test_vpc_empty_subnet_list_raises(self, env):
        _set_vpc_env(env, subnets=" , ")
        with pytest.raises(RuntimeError, match="AC_SUBNET_IDS"):
            resolve_network_config()

    def test_legacy_single_subnet_var_is_not_read(self, env):
        _set_vpc_env(env)
        env.delenv("AC_SUBNET_IDS")
        env.setenv("AC_SUBNET_ID", "subnet-legacy")
        with pytest.raises(RuntimeError, match="AC_SUBNET_IDS"):
            resolve_network_config()


# ---------------------------------------------------------------------------
# build_browser_config
# ---------------------------------------------------------------------------


class TestBuildBrowserConfig:
    def test_public_minimal(self, env):
        config = build_browser_config(
            unique_id="abc12",
            execution_id="ex-1",
            artefact_bucket="studio-artefacts",
            artefact_prefix="uc-1/ex-1/recording/",
            browser_policy_s3_path=None,
        )
        assert config["name"] == "nova_act_qa_studio_abc12"
        assert config["networkConfiguration"] == {"networkMode": "PUBLIC"}
        assert config["description"] == "PUBLIC browser for ex-1"
        assert config["executionRoleArn"] == "arn:aws:iam::1:role/nova-act"
        assert config["recording"]["s3Location"] == {
            "bucket": "studio-artefacts",
            "prefix": "uc-1/ex-1/recording/",
        }
        assert "enterprisePolicies" not in config
        # clientToken is a random UUID — just verify it exists.
        assert "clientToken" in config

    def test_vpc_includes_vpc_config(self, env):
        _set_vpc_env(env)
        config = build_browser_config(
            unique_id="abc12", execution_id="ex-1",
            artefact_bucket="b", artefact_prefix="p/",
            browser_policy_s3_path=None,
        )
        assert config["networkConfiguration"] == {
            "networkMode": "VPC",
            "vpcConfig": {
                "securityGroups": ["sg-1"],
                "subnets": ["subnet-1", "subnet-2"],
            },
        }
        assert config["description"] == "VPC browser for ex-1"

    @pytest.mark.parametrize("vpc", [False, True])
    def test_policy_and_recording_identical_in_both_modes(self, env, vpc):
        if vpc:
            _set_vpc_env(env)
        config = build_browser_config(
            unique_id="x", execution_id="ex",
            artefact_bucket="b", artefact_prefix="uc/ex/recording/",
            browser_policy_s3_path="policies/acme.json",
        )
        assert config["recording"] == {
            "enabled": True,
            "s3Location": {"bucket": "b", "prefix": "uc/ex/recording/"},
        }
        assert config["enterprisePolicies"][0]["location"]["s3"] == {
            "bucket": "b", "prefix": "policies/acme.json",
        }

    def test_enterprise_policy_attached(self, env):
        config = build_browser_config(
            unique_id="x", execution_id="ex",
            artefact_bucket="b", artefact_prefix="p/",
            browser_policy_s3_path="policies/acme.json",
        )
        assert config["enterprisePolicies"] == [
            {
                "type": "MANAGED",
                "location": {
                    "s3": {
                        "bucket": "b",
                        "prefix": "policies/acme.json",
                    },
                },
            },
        ]

    def test_missing_execution_role_raises(self, env):
        env.delenv("BEDROCK_EXECUTION_ROLE")
        with pytest.raises(RuntimeError, match="BEDROCK_EXECUTION_ROLE"):
            build_browser_config(
                unique_id="x", execution_id="ex",
                artefact_bucket="b", artefact_prefix="p/",
                browser_policy_s3_path=None,
            )


# ---------------------------------------------------------------------------
# _wait_for_browser_ready
# ---------------------------------------------------------------------------


class TestWaitForBrowserReady:
    def test_returns_when_ready_immediately(self, monkeypatch):
        import time
        cp = MagicMock()
        cp.get_browser.return_value = _ready_response()
        _wait_for_browser_ready(cp, "b-1", start_time=time.time())
        cp.get_browser.assert_called_once_with(browserId="b-1")

    def test_polls_until_ready(self, monkeypatch):
        import time
        cp = MagicMock()
        cp.get_browser.side_effect = [
            _creating_response(),
            _creating_response(),
            _ready_response(),
        ]
        # Skip sleep so the test is instant.
        monkeypatch.setattr(
            "qa_studio_cli.runner.browser.agentcore.time.sleep",
            lambda _: None,
        )
        _wait_for_browser_ready(cp, "b-1", start_time=time.time())
        assert cp.get_browser.call_count == 3

    def test_failed_status_raises(self, monkeypatch):
        import time
        cp = MagicMock()
        cp.get_browser.return_value = {"status": "FAILED"}
        with pytest.raises(RuntimeError, match="FAILED"):
            _wait_for_browser_ready(cp, "b-1", start_time=time.time())

    def test_timeout_raises(self, monkeypatch):
        import time
        cp = MagicMock()
        cp.get_browser.return_value = _creating_response()
        monkeypatch.setattr(
            "qa_studio_cli.runner.browser.agentcore.time.sleep",
            lambda _: None,
        )
        monkeypatch.setattr(
            "qa_studio_cli.runner.browser.agentcore._BROWSER_READY_TIMEOUT_S",
            0.0,
        )
        with pytest.raises(RuntimeError, match="did not reach READY"):
            _wait_for_browser_ready(cp, "b-1", start_time=time.time())

    def test_does_not_exist_raises(self, monkeypatch):
        import time
        cp = MagicMock()
        cp.get_browser.side_effect = Exception("ResourceNotFound: does not exist")
        with pytest.raises(RuntimeError, match="not found during status check"):
            _wait_for_browser_ready(cp, "b-1", start_time=time.time())


# ---------------------------------------------------------------------------
# _safe_teardown
# ---------------------------------------------------------------------------


class TestSafeTeardown:
    def test_stops_and_deletes(self):
        browser_session = MagicMock()
        cp = MagicMock()
        _safe_teardown(browser_session, cp, "b-1")
        browser_session.stop.assert_called_once()
        cp.delete_browser.assert_called_once_with(browserId="b-1")

    def test_swallows_stop_failure(self):
        browser_session = MagicMock()
        browser_session.stop.side_effect = RuntimeError("boom")
        cp = MagicMock()
        # Must not raise.
        _safe_teardown(browser_session, cp, "b-1")
        cp.delete_browser.assert_called_once_with(browserId="b-1")

    def test_swallows_delete_failure(self):
        browser_session = MagicMock()
        cp = MagicMock()
        cp.delete_browser.side_effect = RuntimeError("boom")
        # Must not raise.
        _safe_teardown(browser_session, cp, "b-1")


# ---------------------------------------------------------------------------
# Provisioner end-to-end (mocked)
# ---------------------------------------------------------------------------


class TestProvisionHappyPath:
    def test_returns_handle_with_cdp_and_live_view(self, env):
        provisioner = AgentCoreBrowserProvisioner()

        cp = MagicMock()
        cp.create_browser.return_value = {"browserId": "b-xyz"}
        cp.get_browser.return_value = _ready_response()

        browser_session = MagicMock()
        browser_session.generate_ws_headers.return_value = (
            "wss://agent.example/cdp",
            {"x-agentcore-auth": "tok"},
        )
        browser_session.generate_live_view_url.return_value = (
            "https://live.example/session-xyz"
        )
        BrowserClientStub = MagicMock(return_value=browser_session)

        with patch(
            "qa_studio_cli.runner.browser.agentcore._create_control_plane_client",
            return_value=cp,
        ), patch(
            "bedrock_agentcore.tools.browser_client.BrowserClient",
            BrowserClientStub,
        ):
            handle = provisioner.provision({
                "usecase_id": "uc-1",
                "execution_id": "ex-1",
                "region": "us-east-1",
                "unique_id": "abc12",
                "starting_url": "https://app.example/",
            })

        assert isinstance(handle, BrowserHandle)
        assert handle.nova_kwargs == {
            "cdp_endpoint_url": "wss://agent.example/cdp",
            "cdp_headers": {"x-agentcore-auth": "tok"},
            "starting_page": "https://app.example/",
        }
        assert handle.live_view_url == "https://live.example/session-xyz"
        assert handle.metadata == {"browser_id": "b-xyz", "region": "us-east-1"}
        assert callable(handle.teardown)

        # Teardown closure stops the session and deletes the browser.
        handle.teardown()
        browser_session.stop.assert_called_once()
        cp.delete_browser.assert_called_once_with(browserId="b-xyz")

    def test_live_view_failure_is_non_fatal(self, env):
        provisioner = AgentCoreBrowserProvisioner()
        cp = MagicMock()
        cp.create_browser.return_value = {"browserId": "b-1"}
        cp.get_browser.return_value = _ready_response()
        browser_session = MagicMock()
        browser_session.generate_ws_headers.return_value = ("wss://x/", {})
        browser_session.generate_live_view_url.side_effect = RuntimeError("no live")

        with patch(
            "qa_studio_cli.runner.browser.agentcore._create_control_plane_client",
            return_value=cp,
        ), patch(
            "bedrock_agentcore.tools.browser_client.BrowserClient",
            return_value=browser_session,
        ):
            handle = provisioner.provision({
                "usecase_id": "uc", "execution_id": "ex",
            })
        assert handle.live_view_url is None
        # CDP still wired.
        assert handle.nova_kwargs["cdp_endpoint_url"] == "wss://x/"


class TestProvisionErrorPaths:
    def test_vpc_mode_sends_vpc_config_to_create_browser(self, env):
        _set_vpc_env(env)
        cp = MagicMock()
        cp.create_browser.return_value = {"browserId": "b-1"}
        cp.get_browser.return_value = _ready_response()
        browser_session = MagicMock()
        browser_session.generate_ws_headers.return_value = ("wss://x/", {})
        with patch(
            "qa_studio_cli.runner.browser.agentcore._create_control_plane_client",
            return_value=cp,
        ), patch(
            "bedrock_agentcore.tools.browser_client.BrowserClient",
            return_value=browser_session,
        ):
            AgentCoreBrowserProvisioner().provision({
                "usecase_id": "uc", "execution_id": "ex",
            })
        kwargs = cp.create_browser.call_args.kwargs
        assert kwargs["networkConfiguration"] == {
            "networkMode": "VPC",
            "vpcConfig": {
                "securityGroups": ["sg-1"],
                "subnets": ["subnet-1", "subnet-2"],
            },
        }
        assert kwargs["recording"]["s3Location"]["prefix"] == "uc/ex/recording/"

    def test_vpc_mode_missing_var_raises_before_any_aws_call(self, env):
        env.setenv("AGENT_CORE_VPC", "true")
        env.setenv("AC_VPC_ID", "vpc-1")
        cp = MagicMock()
        with patch(
            "qa_studio_cli.runner.browser.agentcore._create_control_plane_client",
            return_value=cp,
        ) as factory, pytest.raises(RuntimeError, match="AC_SUBNET_IDS"):
            AgentCoreBrowserProvisioner().provision({"execution_id": "ex"})
        cp.create_browser.assert_not_called()
        # The request is built before the control-plane client exists.
        factory.assert_not_called()

    def test_missing_bucket_raises(self, env):
        env.delenv("S3_BUCKET")
        provisioner = AgentCoreBrowserProvisioner()
        with pytest.raises(RuntimeError, match="S3_BUCKET"):
            provisioner.provision({"execution_id": "ex"})

    def test_missing_execution_id_raises(self, env):
        provisioner = AgentCoreBrowserProvisioner()
        with pytest.raises(RuntimeError, match="execution_id is required"):
            provisioner.provision({})

    def test_missing_extra_raises_clear_error(self, env, monkeypatch):
        """When bedrock_agentcore isn't installed, provision raises an
        AgentCoreNotInstalledError with an install hint."""
        provisioner = AgentCoreBrowserProvisioner()

        # Delete the stub so the import inside provision() fails cleanly.
        monkeypatch.delitem(
            sys.modules, "bedrock_agentcore.tools.browser_client", raising=False,
        )
        monkeypatch.delitem(sys.modules, "bedrock_agentcore.tools", raising=False)
        monkeypatch.delitem(sys.modules, "bedrock_agentcore", raising=False)

        import builtins
        real_import = builtins.__import__

        def _no_agentcore(name, *a, **kw):
            if name.startswith("bedrock_agentcore"):
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _no_agentcore)

        with pytest.raises(AgentCoreNotInstalledError, match="qa-studio\\[agentcore\\]"):
            provisioner.provision({"execution_id": "ex"})
