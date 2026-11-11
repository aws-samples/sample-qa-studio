"""Electron browser provisioner — QA Studio launches the desktop app itself.

Electron apps expose the Chrome DevTools Protocol when started with
``--remote-debugging-port``.  This provisioner owns the whole process
lifecycle so a test run gets a fresh, isolated application instance:

1. spawn ``<exe> --remote-debugging-port=0 --user-data-dir=<dir> <app args>``
   in its own process group;
2. read the ``DevTools listening on ws://127.0.0.1:<port>/…`` line from
   stderr (ephemeral port, loopback only — we never pass
   ``--remote-debugging-address``);
3. poll ``http://127.0.0.1:<port>/json/list`` until the renderer's first
   ``page`` target exists;
4. hand NovaAct the websocket URL plus two kwargs the spike proved
   necessary (``.kiro/docs/electron-testing/design.md``):

   * ``cdp_use_existing_page=True`` — Electron does not implement
     ``Target.createTarget``, so NovaAct's default ``context.new_page()``
     fails with *Protocol error (Target.createTarget): Not supported*.
     With this flag NovaAct attaches to ``context.pages[-1]`` and skips
     the ``starting_page`` navigation entirely.
   * ``ignore_screen_dims_check=True`` — the window size is controlled by
     the application, not by us; downgrade NovaAct's viewport check to a
     warning.

``teardown`` SIGTERMs the process group, waits a grace period and then
SIGKILLs — Electron ignores SIGTERM when it has no TTY (observed in the
spike), so escalation is the normal path, not the exception.

Dispatch is driven by the usecase's ``test_platform == "electron"`` (like
mobile), not by ``--browser``; see ``ExecutionEngine``.
"""

from __future__ import annotations

import logging
import os
import plistlib
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Deque, Dict, Mapping, Optional, Sequence

import requests

from qa_studio_cli.runner.browser.handle import BrowserHandle

logger = logging.getLogger(__name__)

#: Env var overriding how long we wait for the DevTools line and the
#: first page target (seconds).
START_TIMEOUT_ENV = "QA_STUDIO_ELECTRON_START_TIMEOUT"
DEFAULT_START_TIMEOUT_SECONDS = 30.0
DEFAULT_TERM_GRACE_SECONDS = 5.0

_DEVTOOLS_LINE = re.compile(
    r"DevTools listening on (?P<ws>ws://127\.0\.0\.1:(?P<port>\d+)/devtools/browser/[0-9a-fA-F-]+)"
)
_STDERR_TAIL_LINES = 20


class ElectronStartError(RuntimeError):
    """The Electron app did not come up in a testable state."""


#: CFBundleIdentifier of the unbranded Electron shell (``electron`` npm
#: package). When this is the launched bundle, the real application is
#: whatever ``app_args`` points at, so the identifier says nothing about it.
GENERIC_ELECTRON_BUNDLE_ID = "com.github.Electron"


@dataclass(frozen=True)
class ElectronExecutable:
    """What ``resolve_electron_executable`` found.

    ``bundle_id`` is the ``.app``'s ``CFBundleIdentifier`` when the path was
    a bundle that declares one; ``None`` for bare executables.
    """

    path: str
    bundle_id: Optional[str] = None


@dataclass(frozen=True)
class ElectronLaunchConfig:
    """How to launch the application under test.

    ``app_path`` is a macOS ``.app`` bundle or a bare executable (e.g. the
    ``electron`` binary, in which case the app directory goes into
    ``app_args``).  ``user_data_dir`` is optional — by default every run
    gets a fresh temp profile that is deleted at teardown.
    """

    app_path: str
    app_args: Sequence[str] = field(default_factory=tuple)
    user_data_dir: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.app_path:
            raise ValueError("app_path is required for Electron usecases (--app-path)")
        # Normalise to a tuple so the dataclass stays hashable/frozen-safe.
        object.__setattr__(self, "app_args", tuple(self.app_args))


def resolve_electron_executable(app_path: str) -> ElectronExecutable:
    """Translate ``app_path`` into the binary to spawn.

    * ``Foo.app`` → ``Foo.app/Contents/MacOS/<CFBundleExecutable>`` (read
      from ``Info.plist`` so renamed bundles still work), plus the bundle's
      ``CFBundleIdentifier`` for the usecase's ``bundle_id`` check.
    * anything else must be an existing executable file.
    """
    path = Path(app_path)
    if not path.exists():
        raise ValueError(f"Electron app not found: {app_path}")

    if path.is_dir() and path.suffix == ".app":
        plist_path = path / "Contents" / "Info.plist"
        if not plist_path.is_file():
            raise ValueError(
                f"{app_path} is not a valid .app bundle: missing Contents/Info.plist"
            )
        try:
            with open(plist_path, "rb") as fh:
                info = plistlib.load(fh)
        except (OSError, plistlib.InvalidFileException) as exc:
            raise ValueError(f"Could not read {plist_path}: {exc}") from exc
        exe_name = info.get("CFBundleExecutable")
        if not exe_name:
            raise ValueError(f"{plist_path} has no CFBundleExecutable entry")
        exe = path / "Contents" / "MacOS" / exe_name
        if not exe.is_file():
            raise ValueError(f"Bundle executable not found: {exe}")
        bundle_id = info.get("CFBundleIdentifier") or None
        return ElectronExecutable(path=str(exe), bundle_id=bundle_id)

    if path.is_dir():
        raise ValueError(
            f"{app_path} is a directory but not a .app bundle. Pass the .app "
            "bundle or the executable (and the app directory via --app-arg)."
        )
    if not os.access(path, os.X_OK):
        raise ValueError(f"Electron app is not executable: {app_path}")
    return ElectronExecutable(path=str(path))


def verify_bundle_id(executable: ElectronExecutable, expected: Optional[str]) -> None:
    """Refuse to launch an app whose ``CFBundleIdentifier`` is not ``expected``.

    ``expected`` is the usecase's optional ``bundle_id``. The check is
    skipped (with an INFO line) when nothing can be compared: no expected
    value, a bare executable, a bundle without an identifier, or the
    generic Electron shell used for unpackaged dev builds.
    """
    if not expected:
        return
    actual = executable.bundle_id
    if actual is None or actual == GENERIC_ELECTRON_BUNDLE_ID:
        logger.info(
            "Cannot verify bundle id %s: launched %s is %s",
            expected, executable.path,
            "a bare executable" if actual is None else "the generic Electron shell",
        )
        return
    if actual != expected:
        raise ElectronStartError(
            f"Bundle id mismatch: the usecase expects {expected} but "
            f"{executable.path} is {actual}. Pass the right --app-path "
            "or update the usecase's bundle_id."
        )


def _start_timeout_from_env(default: float) -> float:
    raw = os.environ.get(START_TIMEOUT_ENV)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{START_TIMEOUT_ENV} must be a number of seconds, got {raw!r}"
        ) from exc
    if value <= 0:
        raise ValueError(f"{START_TIMEOUT_ENV} must be positive, got {raw!r}")
    return value


class _StderrReader:
    """Drain a process' stderr on a helper thread.

    Electron (and the app inside it) can be chatty; if nobody reads the
    pipe the process blocks once the buffer fills.  We keep a bounded
    tail for error messages and hand the DevTools URL over via an event.
    """

    def __init__(self, stream) -> None:  # type: ignore[no-untyped-def]
        self._stream = stream
        self.tail: Deque[str] = deque(maxlen=_STDERR_TAIL_LINES)
        self.devtools_ws: Optional[str] = None
        self.devtools_port: Optional[int] = None
        self.found = threading.Event()
        self._thread = threading.Thread(target=self._run, name="electron-stderr", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            for line in self._stream:
                stripped = line.rstrip("\n")
                if stripped:
                    self.tail.append(stripped)
                if not self.found.is_set():
                    match = _DEVTOOLS_LINE.search(stripped)
                    if match:
                        self.devtools_ws = match.group("ws")
                        self.devtools_port = int(match.group("port"))
                        self.found.set()
        except (OSError, ValueError):
            # Pipe closed underneath us during teardown — nothing to do.
            pass
        finally:
            # Unblock any waiter even if the line never came.
            self.found.set()

    def tail_text(self) -> str:
        return "\n".join(self.tail)


class ElectronBrowserProvisioner:
    """Launch an Electron app and expose it to NovaAct over CDP."""

    name: ClassVar[str] = "electron"

    def __init__(
        self,
        config: ElectronLaunchConfig,
        *,
        env: Optional[Mapping[str, str]] = None,
        start_timeout: Optional[float] = None,
        term_grace: float = DEFAULT_TERM_GRACE_SECONDS,
    ) -> None:
        self._config = config
        self._extra_env = dict(env or {})
        self._start_timeout = (
            start_timeout
            if start_timeout is not None
            else _start_timeout_from_env(DEFAULT_START_TIMEOUT_SECONDS)
        )
        self._term_grace = term_grace
        self._process: Optional[subprocess.Popen[str]] = None
        self._reader: Optional[_StderrReader] = None
        self._user_data_dir: Optional[str] = None
        self._owns_user_data_dir = False
        self._lock = threading.Lock()

    @property
    def config(self) -> ElectronLaunchConfig:
        return self._config

    # ------------------------------------------------------------------
    # BrowserProvisioner protocol
    # ------------------------------------------------------------------

    def provision(self, context: Dict[str, Any]) -> BrowserHandle:
        resolved = resolve_electron_executable(self._config.app_path)
        verify_bundle_id(resolved, context.get("bundle_id"))
        executable = resolved.path

        if self._config.user_data_dir:
            self._user_data_dir = self._config.user_data_dir
            self._owns_user_data_dir = False
        else:
            self._user_data_dir = tempfile.mkdtemp(prefix="qa-studio-electron-")
            self._owns_user_data_dir = True

        argv = [
            executable,
            "--remote-debugging-port=0",
            f"--user-data-dir={self._user_data_dir}",
            *self._config.app_args,
        ]
        # app_args may be anything the operator chose; log at INFO only.
        # Secrets must travel through ``secret`` steps, never argv.
        logger.info("Launching Electron app: %s", " ".join(argv))

        try:
            self._process = self._spawn(argv)
            assert self._process.stderr is not None
            self._reader = _StderrReader(self._process.stderr)

            deadline = time.monotonic() + self._start_timeout
            ws_url = self._await_devtools(deadline)
            page_url = self._await_page_target(self._reader.devtools_port, deadline)
        except Exception:
            # Leave nothing running or half-created behind a failed start.
            self.teardown()
            raise

        pid = self._process.pid
        logger.info(
            "Electron app ready (pid=%s, port=%s, page=%s)",
            pid, self._reader.devtools_port, page_url,
        )

        nova_kwargs: Dict[str, Any] = {
            "cdp_endpoint_url": ws_url,
            # No ``cdp_headers``: Playwright only serialises a *truthy*
            # headers dict, so an empty ``{}`` reaches the protocol as an
            # object and ``connect_over_cdp`` fails with
            # "headers: expected array, got object". Omitting the key lets
            # NovaAct pass ``None``.
            # Spike findings — see module docstring.
            "cdp_use_existing_page": True,
            "ignore_screen_dims_check": True,
            # Informational: NovaAct skips the goto when attaching to the
            # existing page, but the engine logs it and tests pin it.
            "starting_page": page_url,
        }
        return BrowserHandle(
            nova_kwargs=nova_kwargs,
            teardown=self.teardown,
            metadata={
                "pid": pid,
                "port": self._reader.devtools_port,
                "user_data_dir": self._user_data_dir,
                "usecase_id": context.get("usecase_id"),
                "bundle_id": resolved.bundle_id,
            },
        )

    def teardown(self) -> None:
        """Stop the app and remove the temp profile. Idempotent."""
        with self._lock:
            process, self._process = self._process, None
            reader, self._reader = self._reader, None
            udd, self._user_data_dir = self._user_data_dir, None
            owns_udd, self._owns_user_data_dir = self._owns_user_data_dir, False

        if process is not None:
            self._kill_process_group(process)
            if process.stderr is not None:
                try:
                    process.stderr.close()
                except OSError:
                    pass
        if reader is not None:
            reader.found.set()

        if udd and owns_udd:
            shutil.rmtree(udd, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _spawn(self, argv: Sequence[str]) -> subprocess.Popen[str]:
        env = {**os.environ, **self._extra_env}
        return subprocess.Popen(  # noqa: S603 — argv is operator-controlled, not user input
            list(argv),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )

    def _await_devtools(self, deadline: float) -> str:
        assert self._process is not None and self._reader is not None
        reader = self._reader
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ElectronStartError(
                    f"Electron did not print 'DevTools listening on …' within "
                    f"{self._start_timeout:.0f}s. stderr tail:\n{reader.tail_text()}"
                )
            if reader.found.wait(timeout=min(remaining, 0.25)):
                if reader.devtools_ws:
                    return reader.devtools_ws
                # Reader finished without the line: process exited (or closed stderr).
                code = self._process.poll()
                if code is None:
                    # stderr closed but the process is alive; give it a moment
                    # to exit before deciding, so the error names the code.
                    try:
                        code = self._process.wait(timeout=min(remaining, 1.0))
                    except subprocess.TimeoutExpired:
                        pass
                raise ElectronStartError(
                    f"Electron exited with code {code} before exposing DevTools. "
                    f"stderr tail:\n{reader.tail_text()}"
                )
            code = self._process.poll()
            if code is not None and not reader.found.is_set():
                # Let the reader flush the last lines before we report.
                reader.found.wait(timeout=0.5)
                if reader.devtools_ws:
                    return reader.devtools_ws
                raise ElectronStartError(
                    f"Electron exited with code {code} before exposing DevTools. "
                    f"stderr tail:\n{reader.tail_text()}"
                )

    def _await_page_target(self, port: Optional[int], deadline: float) -> str:
        assert port is not None
        url = f"http://127.0.0.1:{port}/json/list"
        last_error: Optional[str] = None
        while time.monotonic() < deadline:
            try:
                response = requests.get(url, timeout=2)
                response.raise_for_status()
                targets = response.json()
                pages = [t for t in targets if isinstance(t, dict) and t.get("type") == "page"]
                if pages:
                    return str(pages[0].get("url", ""))
                last_error = f"no page target yet ({len(targets)} targets)"
            except (requests.RequestException, ValueError) as exc:
                last_error = str(exc)
            if self._process is not None and self._process.poll() is not None:
                raise ElectronStartError(
                    f"Electron exited with code {self._process.returncode} before "
                    f"opening a window. stderr tail:\n"
                    f"{self._reader.tail_text() if self._reader else ''}"
                )
            time.sleep(0.25)
        raise ElectronStartError(
            f"Electron exposed DevTools on port {port} but no page target appeared "
            f"within {self._start_timeout:.0f}s (last: {last_error})."
        )

    def _kill_process_group(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            return

        def _signal(sig: int) -> None:
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                pass

        _signal(signal.SIGTERM)
        try:
            process.wait(timeout=self._term_grace)
            return
        except subprocess.TimeoutExpired:
            logger.info(
                "Electron (pid=%s) ignored SIGTERM for %.1fs; sending SIGKILL",
                process.pid, self._term_grace,
            )
        _signal(signal.SIGKILL)
        try:
            process.wait(timeout=self._term_grace)
        except subprocess.TimeoutExpired:
            logger.warning(
                "Electron (pid=%s) survived SIGKILL wait; it may be orphaned", process.pid,
            )
