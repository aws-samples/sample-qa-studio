"""Tests for the CdpExternalBrowserProvisioner."""

from __future__ import annotations

import json

import pytest

from qa_studio_cli.runner.browser import (
    BrowserHandle,
    CdpExternalBrowserProvisioner,
)


class TestProvision:
    def test_sets_cdp_kwargs(self):
        provisioner = CdpExternalBrowserProvisioner(
            cdp_endpoint_url="wss://browser.example/cdp",
            cdp_headers={"x-auth": "secret"},
        )
        handle = provisioner.provision({"starting_url": "https://target.example/"})
        assert handle.nova_kwargs == {
            "cdp_endpoint_url": "wss://browser.example/cdp",
            "cdp_headers": {"x-auth": "secret"},
            "starting_page": "https://target.example/",
        }
        # We did not create the browser; teardown is a no-op.
        assert handle.teardown is None
        assert isinstance(handle, BrowserHandle)

    def test_headers_default_to_empty(self):
        provisioner = CdpExternalBrowserProvisioner(
            cdp_endpoint_url="wss://browser.example/cdp",
        )
        handle = provisioner.provision({"starting_url": "https://x.test/"})
        assert handle.nova_kwargs["cdp_headers"] == {}

    def test_rejects_empty_endpoint(self):
        with pytest.raises(ValueError, match="cdp_endpoint_url is required"):
            CdpExternalBrowserProvisioner(cdp_endpoint_url="")

    def test_rejects_none_endpoint(self):
        with pytest.raises(ValueError, match="cdp_endpoint_url is required"):
            CdpExternalBrowserProvisioner(cdp_endpoint_url=None)  # type: ignore[arg-type]


class TestFromFlags:
    def test_reads_headers_from_file(self, tmp_path):
        headers_file = tmp_path / "headers.json"
        headers_file.write_text(json.dumps({"x-auth": "hunter2"}))
        provisioner = CdpExternalBrowserProvisioner.from_flags(
            cdp_endpoint_url="wss://x.test/",
            cdp_headers_file=str(headers_file),
        )
        handle = provisioner.provision({"starting_url": "https://s.test/"})
        assert handle.nova_kwargs["cdp_headers"] == {"x-auth": "hunter2"}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="cdp_headers_file not found"):
            CdpExternalBrowserProvisioner.from_flags(
                cdp_endpoint_url="wss://x.test/",
                cdp_headers_file=str(tmp_path / "nope.json"),
            )

    def test_non_json_file_raises(self, tmp_path):
        headers_file = tmp_path / "headers.json"
        headers_file.write_text("this is not JSON")
        with pytest.raises(ValueError, match="not valid JSON"):
            CdpExternalBrowserProvisioner.from_flags(
                cdp_endpoint_url="wss://x.test/",
                cdp_headers_file=str(headers_file),
            )

    def test_json_array_rejected(self, tmp_path):
        # Headers must be an object, not an array or primitive.
        headers_file = tmp_path / "headers.json"
        headers_file.write_text(json.dumps(["x-auth", "value"]))
        with pytest.raises(ValueError, match="must contain a JSON object"):
            CdpExternalBrowserProvisioner.from_flags(
                cdp_endpoint_url="wss://x.test/",
                cdp_headers_file=str(headers_file),
            )

    def test_no_headers_file_means_empty_headers(self):
        provisioner = CdpExternalBrowserProvisioner.from_flags(
            cdp_endpoint_url="wss://x.test/",
            cdp_headers_file=None,
        )
        handle = provisioner.provision({"starting_url": "https://s.test/"})
        assert handle.nova_kwargs["cdp_headers"] == {}

    def test_header_values_coerced_to_strings(self, tmp_path):
        # A user might write integer values in the headers file; coerce.
        headers_file = tmp_path / "headers.json"
        headers_file.write_text(json.dumps({"x-retry-count": 3}))
        provisioner = CdpExternalBrowserProvisioner.from_flags(
            cdp_endpoint_url="wss://x.test/",
            cdp_headers_file=str(headers_file),
        )
        handle = provisioner.provision({"starting_url": "https://s.test/"})
        assert handle.nova_kwargs["cdp_headers"] == {"x-retry-count": "3"}
