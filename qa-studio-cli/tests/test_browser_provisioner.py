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


# ---------------------------------------------------------------------------
# record_video_supported helper
# ---------------------------------------------------------------------------

from qa_studio_cli.runner.browser import record_video_supported  # noqa: E402


class TestRecordVideoSupported:
    """Tests for the ``record_video_supported`` predicate.

    NovaAct's rule (``nova_act/tools/browser/default/playwright.py:88``)
    is reproduced in the helper: any kwarg combination that implies a
    CDP connection disqualifies ``record_video=True``. These tests pin
    the predicate so a silent change to the rule fails CI.
    """

    def test_empty_kwargs_support_video(self):
        assert record_video_supported({}) is True

    def test_bundled_chromium_supports_video(self):
        """No CDP-implying flag → recording is available."""
        assert record_video_supported({"starting_page": "https://x/"}) is True

    def test_system_chrome_channel_supports_video(self):
        """``chrome_channel="chrome"`` launches via Playwright, not CDP."""
        kwargs = {"chrome_channel": "chrome", "starting_page": "https://x/"}
        assert record_video_supported(kwargs) is True

    def test_chrome_profile_disables_video(self):
        """``use_default_chrome_browser=True`` → NovaAct refuses video."""
        kwargs = {
            "use_default_chrome_browser": True,
            "clone_user_data_dir": False,
            "user_data_dir": "/tmp/copy",
        }
        assert record_video_supported(kwargs) is False

    def test_cdp_endpoint_url_disables_video(self):
        kwargs = {"cdp_endpoint_url": "wss://remote.example/cdp"}
        assert record_video_supported(kwargs) is False

    def test_both_cdp_flags_still_disables_video(self):
        """Defensive — if both CDP flags are set for some reason,
        recording stays disabled rather than accidentally enabled."""
        kwargs = {
            "cdp_endpoint_url": "wss://remote.example/cdp",
            "use_default_chrome_browser": True,
        }
        assert record_video_supported(kwargs) is False

    def test_mobile_actuator_kwargs_are_supported(self):
        """Mobile path uses an ``actuator`` (Appium) and sidesteps the
        Playwright CDP rule entirely — the helper must not accidentally
        disable video for mobile runs."""
        kwargs = {
            "actuator": object(),  # sentinel — real actuator object
            "starting_page": "https://x/",
            "ignore_screen_dims_check": True,
            "ignore_https_errors": True,
        }
        assert record_video_supported(kwargs) is True

    def test_falsy_cdp_values_do_not_disable_video(self):
        """An empty string / None for a CDP flag must not trip the check."""
        kwargs = {"cdp_endpoint_url": "", "use_default_chrome_browser": False}
        assert record_video_supported(kwargs) is True

    def test_helper_is_exported_from_package(self):
        """Public API check — the helper must be accessible at the
        package root so callers don't have to know the submodule layout."""
        from qa_studio_cli.runner import browser as browser_pkg

        assert "record_video_supported" in browser_pkg.__all__
        assert browser_pkg.record_video_supported({}) is True
