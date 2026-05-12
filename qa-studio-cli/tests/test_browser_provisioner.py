"""Tests for the browser provisioner module.

T2.5 only introduces the protocol + local strategy; agentcore and
cdp-external ship in later tasks. Tests verify the local strategy is a
no-op pass-through that doesn't change runtime behaviour.
"""

from qa_studio_cli.runner.browser import (
    BrowserHandle,
    BrowserProvisioner,
    LocalBrowserProvisioner,
)


class TestBrowserHandle:
    def test_defaults_are_empty(self):
        handle = BrowserHandle()
        assert handle.nova_kwargs == {}
        assert handle.live_view_url is None
        assert handle.teardown is None
        assert handle.metadata == {}

    def test_stores_kwargs(self):
        handle = BrowserHandle(nova_kwargs={"starting_page": "https://example.com"})
        assert handle.nova_kwargs == {"starting_page": "https://example.com"}


class TestLocalBrowserProvisioner:
    def test_name(self):
        assert LocalBrowserProvisioner.name == "local"

    def test_passes_starting_url(self):
        handle = LocalBrowserProvisioner().provision(
            {"starting_url": "https://example.com/"}
        )
        assert handle.nova_kwargs == {"starting_page": "https://example.com/"}
        assert handle.teardown is None
        assert handle.live_view_url is None

    def test_empty_starting_url_still_produces_kwargs(self):
        handle = LocalBrowserProvisioner().provision({})
        assert handle.nova_kwargs == {"starting_page": ""}

    def test_ignores_unknown_context_keys(self):
        handle = LocalBrowserProvisioner().provision({
            "starting_url": "https://example.com/",
            "execution_id": "exec-1",
            "usecase_id": "uc-1",
            "region": "us-east-1",
            "some_unknown_key": "junk",
        })
        # Only starting_page surfaces
        assert handle.nova_kwargs == {"starting_page": "https://example.com/"}

    def test_implements_protocol(self):
        """Duck-typed check: LocalBrowserProvisioner satisfies the Protocol."""
        provisioner: BrowserProvisioner = LocalBrowserProvisioner()
        assert provisioner.name == "local"
        handle = provisioner.provision({"starting_url": "https://x.test/"})
        assert isinstance(handle, BrowserHandle)
