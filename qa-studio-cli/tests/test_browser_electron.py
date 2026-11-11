"""Tests for the ElectronBrowserProvisioner.

The provisioner is exercised against a *real* subprocess — a small Python
script standing in for an Electron binary.  The fake prints the same
``DevTools listening on ws://…`` line Electron prints to stderr, serves
``/json/list`` on the port it chose, and then idles until killed.  That
keeps the tests honest about the three things the provisioner really
does: spawn, parse stderr, poll the DevTools HTTP endpoint, and tear the
process group down.
"""

from __future__ import annotations

import os
import plistlib
import signal
import stat
import sys
import textwrap
import time
from pathlib import Path

import pytest

from qa_studio_cli.runner.browser import (
    BrowserHandle,
    ElectronBrowserProvisioner,
    ElectronLaunchConfig,
    ElectronStartError,
    record_video_supported,
    resolve_electron_executable,
)
from qa_studio_cli.runner.browser.electron import (
    GENERIC_ELECTRON_BUNDLE_ID,
    ElectronExecutable,
)


# ---------------------------------------------------------------------------
# Fake Electron binary
# ---------------------------------------------------------------------------

FAKE_ELECTRON = textwrap.dedent(
    """
    import http.server, json, os, signal, sys, threading, time

    mode = os.environ.get("FAKE_ELECTRON_MODE", "ok")
    argv_dump = os.environ.get("FAKE_ELECTRON_ARGV_FILE")
    if argv_dump:
        with open(argv_dump, "w") as fh:
            json.dump(sys.argv[1:], fh)

    if mode == "exit-early":
        print("Something went badly wrong", file=sys.stderr)
        print("Error: cannot find module", file=sys.stderr)
        sys.exit(3)

    if mode == "silent":
        # Never prints the DevTools line.
        time.sleep(60)
        sys.exit(0)

    if mode == "ignore-sigterm":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def do_GET(self):
            if self.path == "/json/list":
                if mode == "no-page":
                    body = json.dumps([{"type": "service_worker", "url": "sw"}])
                else:
                    body = json.dumps([
                        {"type": "service_worker", "url": "chrome-extension://x/sw.js"},
                        {"type": "page", "url": "file:///app/out/renderer/index.html",
                         "title": "Product Harness"},
                    ])
                data = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404); self.end_headers()

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # Electron prints a blank line first, then the DevTools line.
    print("", file=sys.stderr)
    print(f"DevTools listening on ws://127.0.0.1:{port}/devtools/browser/"
          "58074136-cf5d-482c-8b54-a092f28b96bc", file=sys.stderr, flush=True)
    # Chatty app: keep writing to stderr so a non-draining reader would block.
    while True:
        print("[app] heartbeat " + "x" * 200, file=sys.stderr, flush=True)
        time.sleep(0.05)
    """
)


@pytest.fixture
def fake_electron(tmp_path: Path) -> Path:
    script = tmp_path / "fake-electron"
    script.write_text(f"#!{sys.executable}\n{FAKE_ELECTRON}")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def _make_bundle(root: Path, fake_electron: Path, *, name="Fake.app", bundle_id="com.example.fake") -> Path:
    bundle = root / name
    macos = bundle / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    exe = macos / "FakeElectron"
    exe.write_bytes(fake_electron.read_bytes())
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    info = {"CFBundleExecutable": "FakeElectron"}
    if bundle_id is not None:
        info["CFBundleIdentifier"] = bundle_id
    with open(bundle / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump(info, fh)
    return bundle


@pytest.fixture
def fake_app_bundle(tmp_path: Path, fake_electron: Path) -> Path:
    """A minimal ``.app`` bundle whose Info.plist points at the fake binary."""
    return _make_bundle(tmp_path, fake_electron)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        # Reap zombie children so os.kill(pid, 0) stops succeeding.
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return True
        time.sleep(0.05)
    return not _pid_alive(pid)


# ---------------------------------------------------------------------------
# resolve_electron_executable
# ---------------------------------------------------------------------------


class TestResolveExecutable:
    def test_app_bundle_resolves_via_info_plist(self, fake_app_bundle):
        resolved = resolve_electron_executable(str(fake_app_bundle))
        assert isinstance(resolved, ElectronExecutable)
        assert resolved.path == str(fake_app_bundle / "Contents" / "MacOS" / "FakeElectron")
        assert resolved.bundle_id == "com.example.fake"

    def test_app_bundle_without_identifier(self, tmp_path, fake_electron):
        bundle = _make_bundle(tmp_path, fake_electron, bundle_id=None)
        assert resolve_electron_executable(str(bundle)).bundle_id is None

    def test_app_bundle_without_plist_raises(self, tmp_path):
        bundle = tmp_path / "Broken.app"
        (bundle / "Contents" / "MacOS").mkdir(parents=True)
        with pytest.raises(ValueError, match="Info.plist"):
            resolve_electron_executable(str(bundle))

    def test_plain_executable_passes_through(self, fake_electron):
        resolved = resolve_electron_executable(str(fake_electron))
        assert resolved.path == str(fake_electron)
        assert resolved.bundle_id is None

    def test_missing_path_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            resolve_electron_executable(str(tmp_path / "nope"))

    def test_non_executable_file_raises(self, tmp_path):
        f = tmp_path / "notexec"
        f.write_text("hi")
        f.chmod(0o644)
        with pytest.raises(ValueError, match="not executable"):
            resolve_electron_executable(str(f))


# ---------------------------------------------------------------------------
# ElectronLaunchConfig
# ---------------------------------------------------------------------------


class TestLaunchConfig:
    def test_defaults(self):
        cfg = ElectronLaunchConfig(app_path="/x/App.app")
        assert cfg.app_args == ()
        assert cfg.user_data_dir is None

    def test_is_frozen(self):
        cfg = ElectronLaunchConfig(app_path="/x/App.app")
        with pytest.raises(Exception):
            cfg.app_path = "/y"  # type: ignore[misc]

    def test_requires_app_path(self):
        with pytest.raises(ValueError, match="app_path"):
            ElectronLaunchConfig(app_path="")

    def test_app_args_normalised_to_tuple(self):
        cfg = ElectronLaunchConfig(app_path="/x", app_args=["a", "b"])
        assert cfg.app_args == ("a", "b")


# ---------------------------------------------------------------------------
# provision()
# ---------------------------------------------------------------------------


class TestProvision:
    def test_happy_path(self, fake_electron, tmp_path):
        argv_file = tmp_path / "argv.json"
        env = {"FAKE_ELECTRON_ARGV_FILE": str(argv_file)}
        prov = ElectronBrowserProvisioner(
            ElectronLaunchConfig(app_path=str(fake_electron), app_args=["/some/app-dir", "--flag"]),
            env=env,
        )
        handle = prov.provision({"usecase_id": "u-1"})
        try:
            assert isinstance(handle, BrowserHandle)
            kw = handle.nova_kwargs
            assert kw["cdp_endpoint_url"].startswith("ws://127.0.0.1:")
            assert kw["cdp_endpoint_url"].endswith(
                "/devtools/browser/58074136-cf5d-482c-8b54-a092f28b96bc"
            )
            # An empty headers dict breaks Playwright's connect_over_cdp
            # ("headers: expected array, got object") — the key must be absent.
            assert "cdp_headers" not in kw
            # Spike findings: Electron has no Target.createTarget, so Nova Act
            # must attach to the existing page; the window size is app-controlled.
            assert kw["cdp_use_existing_page"] is True
            assert kw["ignore_screen_dims_check"] is True
            assert kw["starting_page"] == "file:///app/out/renderer/index.html"
            assert record_video_supported(kw) is False
            assert handle.metadata["pid"] > 0
            assert handle.metadata["port"] == int(kw["cdp_endpoint_url"].split(":")[2].split("/")[0])
            assert handle.teardown is not None

            import json
            argv = json.loads(argv_file.read_text())
            assert argv[0] == "--remote-debugging-port=0"
            assert argv[1].startswith("--user-data-dir=")
            assert argv[2:] == ["/some/app-dir", "--flag"]
            # Loopback only: never widen the debug surface.
            assert not any(a.startswith("--remote-debugging-address") for a in argv)
            assert not any(a.startswith("--remote-allow-origins") for a in argv)
        finally:
            handle.teardown()

    def test_app_bundle_is_launched_via_its_executable(self, fake_app_bundle):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_app_bundle)))
        handle = prov.provision({})
        try:
            assert handle.nova_kwargs["cdp_use_existing_page"] is True
        finally:
            handle.teardown()

    def test_temp_user_data_dir_created_and_removed(self, fake_electron):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_electron)))
        handle = prov.provision({})
        udd = Path(handle.metadata["user_data_dir"])
        assert udd.is_dir()
        handle.teardown()
        assert not udd.exists()

    def test_supplied_user_data_dir_is_used_and_kept(self, fake_electron, tmp_path):
        udd = tmp_path / "profile"
        udd.mkdir()
        (udd / "seed.txt").write_text("keep me")
        prov = ElectronBrowserProvisioner(
            ElectronLaunchConfig(app_path=str(fake_electron), user_data_dir=str(udd)),
        )
        handle = prov.provision({})
        assert handle.metadata["user_data_dir"] == str(udd)
        handle.teardown()
        assert (udd / "seed.txt").read_text() == "keep me"

    def test_process_exits_early_raises_with_stderr_tail(self, fake_electron):
        prov = ElectronBrowserProvisioner(
            ElectronLaunchConfig(app_path=str(fake_electron)),
            env={"FAKE_ELECTRON_MODE": "exit-early"},
        )
        with pytest.raises(ElectronStartError, match="exited with code 3") as exc:
            prov.provision({})
        assert "cannot find module" in str(exc.value)
        # Nothing left behind.
        assert prov._process is None or prov._process.poll() is not None

    def test_timeout_without_devtools_line(self, fake_electron):
        prov = ElectronBrowserProvisioner(
            ElectronLaunchConfig(app_path=str(fake_electron)),
            env={"FAKE_ELECTRON_MODE": "silent"},
            start_timeout=0.5,
        )
        pid_holder = {}
        orig_spawn = prov._spawn

        def _spy(*a, **kw):
            p = orig_spawn(*a, **kw)
            pid_holder["pid"] = p.pid
            return p

        prov._spawn = _spy  # type: ignore[method-assign]
        with pytest.raises(ElectronStartError, match="DevTools listening"):
            prov.provision({})
        # The failed provision must have killed the process it started.
        assert _wait_gone(pid_holder["pid"])

    def test_timeout_waiting_for_page_target(self, fake_electron):
        prov = ElectronBrowserProvisioner(
            ElectronLaunchConfig(app_path=str(fake_electron)),
            env={"FAKE_ELECTRON_MODE": "no-page"},
            start_timeout=0.8,
        )
        with pytest.raises(ElectronStartError, match="page target"):
            prov.provision({})

    def test_start_timeout_from_env(self, fake_electron, monkeypatch):
        monkeypatch.setenv("QA_STUDIO_ELECTRON_START_TIMEOUT", "0.3")
        prov = ElectronBrowserProvisioner(
            ElectronLaunchConfig(app_path=str(fake_electron)),
            env={"FAKE_ELECTRON_MODE": "silent"},
        )
        t0 = time.monotonic()
        with pytest.raises(ElectronStartError):
            prov.provision({})
        assert time.monotonic() - t0 < 5

    def test_invalid_start_timeout_env_raises(self, fake_electron, monkeypatch):
        monkeypatch.setenv("QA_STUDIO_ELECTRON_START_TIMEOUT", "soon")
        with pytest.raises(ValueError, match="QA_STUDIO_ELECTRON_START_TIMEOUT"):
            ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_electron)))


# ---------------------------------------------------------------------------
# bundle id verification
# ---------------------------------------------------------------------------


class TestBundleIdCheck:
    """``context["bundle_id"]`` (from the usecase) is compared with the
    launched .app's CFBundleIdentifier so a suite cannot run against the
    wrong application."""

    def test_matching_bundle_id_launches(self, fake_app_bundle):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_app_bundle)))
        handle = prov.provision({"bundle_id": "com.example.fake"})
        try:
            assert handle.metadata["bundle_id"] == "com.example.fake"
        finally:
            handle.teardown()

    def test_mismatch_refuses_before_spawn(self, fake_app_bundle):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_app_bundle)))
        spawned = []
        prov._spawn = lambda argv: spawned.append(argv) or (_ for _ in ()).throw(AssertionError("must not spawn"))  # type: ignore[method-assign]
        with pytest.raises(ElectronStartError, match="expects com.other.app but .* is com.example.fake"):
            prov.provision({"bundle_id": "com.other.app"})
        assert spawned == []

    def test_generic_electron_shell_is_not_compared(self, tmp_path, fake_electron, caplog):
        # Dev launches use the unbranded Electron.app plus --app-arg <app dir>;
        # its CFBundleIdentifier (com.github.Electron) says nothing about the
        # app under test, so the check is skipped with a log line.
        bundle = _make_bundle(tmp_path, fake_electron, name="Electron.app", bundle_id=GENERIC_ELECTRON_BUNDLE_ID)
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(bundle), app_args=["/some/app"]))
        with caplog.at_level("INFO"):
            handle = prov.provision({"bundle_id": "com.productharness.desktop"})
        try:
            assert "cannot verify" in caplog.text.lower()
        finally:
            handle.teardown()

    def test_no_expected_bundle_id_skips_check(self, fake_app_bundle):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_app_bundle)))
        handle = prov.provision({})
        handle.teardown()

    def test_bare_executable_cannot_be_verified(self, fake_electron, caplog):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_electron)))
        with caplog.at_level("INFO"):
            handle = prov.provision({"bundle_id": "com.example.fake"})
        try:
            assert "cannot verify" in caplog.text.lower()
        finally:
            handle.teardown()


# ---------------------------------------------------------------------------
# teardown()
# ---------------------------------------------------------------------------


class TestTeardown:
    def test_kills_process(self, fake_electron):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_electron)))
        handle = prov.provision({})
        pid = handle.metadata["pid"]
        assert _pid_alive(pid)
        handle.teardown()
        assert _wait_gone(pid)

    def test_escalates_to_sigkill_when_sigterm_ignored(self, fake_electron):
        # Electron ignores SIGTERM without a TTY (spike finding); teardown
        # must escalate instead of leaving an orphan behind.
        prov = ElectronBrowserProvisioner(
            ElectronLaunchConfig(app_path=str(fake_electron)),
            env={"FAKE_ELECTRON_MODE": "ignore-sigterm"},
            term_grace=0.3,
        )
        handle = prov.provision({})
        pid = handle.metadata["pid"]
        handle.teardown()
        assert _wait_gone(pid)

    def test_idempotent(self, fake_electron):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_electron)))
        handle = prov.provision({})
        handle.teardown()
        handle.teardown()  # must not raise
        prov.teardown()  # nor via the provisioner directly

    def test_safe_before_provision(self, fake_electron):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_electron)))
        prov.teardown()  # nothing started — no error

    def test_tolerates_already_dead_process(self, fake_electron):
        prov = ElectronBrowserProvisioner(ElectronLaunchConfig(app_path=str(fake_electron)))
        handle = prov.provision({})
        pid = handle.metadata["pid"]
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        assert _wait_gone(pid)
        handle.teardown()  # must not raise on ProcessLookupError
