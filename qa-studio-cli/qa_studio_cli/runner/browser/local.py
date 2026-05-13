"""Local browser provisioner — NovaAct launches the browser itself.

The provisioner is a thin packager: it decides which NovaAct kwargs
select Chromium vs Chrome vs "Chrome with the user's real profile",
and hands them to the runner. Adding another browser family later
(Firefox once NovaAct supports it, MSEdge, a dev/beta channel) is a
one-entry change to :data:`LOCAL_BROWSER_OPTIONS` — the runner, CLI
flag, and TUI form pick it up automatically from the dict keys.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

from qa_studio_cli.runner.browser.handle import BrowserHandle


logger = logging.getLogger(__name__)


#: Working copy of the user's Chrome profile lives here. NovaAct
#: rejects the system default Chrome directory for CDP automation
#: (see ``_validate_chrome_user_data_dir_ok_for_cdp`` in nova_act) —
#: it needs a separate copy it can drive without fighting a live
#: Chrome instance over profile locks.
CHROME_PROFILE_COPY_DIR = Path.home() / ".qa-studio" / "chrome-profile-copy"


def default_chrome_user_data_dir() -> Optional[Path]:
    """Best-effort OS-default Chrome user-data directory.

    Returns ``None`` on platforms we don't know — the caller surfaces a
    clear error rather than guessing. On the supported triad:

    - **macOS**: ``~/Library/Application Support/Google/Chrome``
    - **Linux**: ``~/.config/google-chrome``
    - **Windows**: ``%LOCALAPPDATA%/Google/Chrome/User Data``

    The path is not validated here (the directory may not exist if
    Chrome has never run) — NovaAct raises its own clear error if so,
    and resolving a non-existent path would fail a separate command
    whose output the user can't see.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    if sys.platform.startswith("linux"):
        return Path.home() / ".config" / "google-chrome"
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "Google" / "Chrome" / "User Data"
    return None


def ensure_chrome_profile_copy(
    source: Optional[Path] = None,
    destination: Optional[Path] = None,
) -> Path:
    """Ensure a CDP-compatible copy of the user's Chrome profile exists.

    NovaAct refuses to point CDP at the system-default Chrome directory
    (locked profile, resource conflicts, and NovaAct's explicit guard).
    We maintain a working copy under ``~/.qa-studio/chrome-profile-copy``
    that NovaAct can drive freely. The copy is created once and reused
    on subsequent runs — Chrome saves back to it, so state accumulates
    naturally. Delete the directory to force a fresh copy from the
    system profile.

    Args:
        source: Override for the system Chrome profile location. Used
            mainly by tests; production callers pass ``None`` to
            auto-detect.
        destination: Override for the working-copy location. Tests
            point this at a tmp dir.

    Returns:
        Path to the working copy, guaranteed to exist on return.

    Raises:
        RuntimeError: Unknown OS, Chrome profile missing, or copy
            failed.
    """
    src = source or default_chrome_user_data_dir()
    if src is None:
        raise RuntimeError(
            "Could not determine the default Chrome user-data directory "
            "for this platform. 'Chrome (your profile)' is not available "
            "here — use a different browser option."
        )
    if not src.exists():
        raise RuntimeError(
            f"Chrome profile not found at {src}. Launch Chrome at least "
            "once before selecting 'Chrome (your profile)'."
        )

    dst = destination or CHROME_PROFILE_COPY_DIR
    if dst.exists():
        return dst

    dst.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Copying Chrome profile from %s to %s (first run only; "
        "this can take a minute)…",
        src, dst,
    )
    try:
        # ``Singleton*`` lock files are Chrome's live-instance markers;
        # copying them confuses the launched browser into thinking
        # another process owns the profile. ``ignore_dangling_symlinks``
        # tolerates broken macOS symlinks Chrome occasionally leaves
        # behind.
        shutil.copytree(
            src,
            dst,
            symlinks=False,
            ignore=shutil.ignore_patterns("Singleton*", "lockfile", "*.lock"),
            ignore_dangling_symlinks=True,
        )
    except Exception:
        # Leave no half-copied directory behind — next run would skip
        # the copy thinking it's valid, then NovaAct fails with a
        # confusing error about missing profile files.
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        raise
    return dst


@dataclass(frozen=True)
class LocalBrowserOption:
    """A user-selectable local-browser profile.

    ``nova_kwargs`` are merged into the ``NovaAct(...)`` constructor
    call when the runner starts the browser. Options that want to
    hide themselves from a specific surface can leave UI strings
    empty and the CLI / TUI will simply skip rendering them.
    """

    key: str
    label: str
    description: str
    nova_kwargs: Dict[str, Any] = field(default_factory=dict)


#: Registry of local-browser options. ``chromium`` is the default
#: (NovaAct's bundled Chromium, fresh profile every run). When a new
#: browser lands, append a single entry here and every caller picks
#: it up via :func:`list_local_browsers` / ``click.Choice``.
LOCAL_BROWSER_OPTIONS: Dict[str, LocalBrowserOption] = {
    "chromium": LocalBrowserOption(
        key="chromium",
        label="Chromium (bundled)",
        description="NovaAct's bundled Chromium, fresh profile every run.",
        nova_kwargs={},
    ),
    "chrome": LocalBrowserOption(
        key="chrome",
        label="Chrome (system)",
        description="System-installed Google Chrome with a fresh profile.",
        nova_kwargs={"chrome_channel": "chrome"},
    ),
    "chrome-profile": LocalBrowserOption(
        key="chrome-profile",
        label="Chrome (your profile)",
        description=(
            "Your installed Chrome with a working copy of your real "
            "user profile (cookies, saved sessions). Copied once to "
            "~/.qa-studio/chrome-profile-copy on first run and reused "
            "after. macOS only — NovaAct doesn't support this path on "
            "Linux or Windows."
        ),
        # ``use_default_chrome_browser=True`` points NovaAct at your
        # Chrome profile; NovaAct then refuses a live profile (would
        # conflict with your running Chrome) so we pair with
        # ``clone_user_data_dir=False`` and, at provision time, point
        # ``user_data_dir`` at a CDP-safe copy. See
        # :func:`ensure_chrome_profile_copy`.
        nova_kwargs={
            "use_default_chrome_browser": True,
            "clone_user_data_dir": False,
        },
    ),
}


def list_local_browsers() -> list[str]:
    """Return the registry keys in insertion order. Used by Click and
    the TUI ``Select`` widget for option rendering."""
    return list(LOCAL_BROWSER_OPTIONS.keys())


class LocalBrowserProvisioner:
    """Default provisioner. Hands NovaAct the starting URL + the chosen
    browser kwargs and exits."""

    name: ClassVar[str] = "local"

    def __init__(
        self,
        browser_key: str = "chromium",
        headless: Optional[bool] = None,
    ) -> None:
        if browser_key not in LOCAL_BROWSER_OPTIONS:
            raise ValueError(
                f"Unknown local browser: {browser_key!r}. "
                f"Valid choices: {', '.join(LOCAL_BROWSER_OPTIONS)}"
            )
        self._browser_key = browser_key
        self._headless = headless

    @property
    def browser_key(self) -> str:
        return self._browser_key

    @property
    def headless(self) -> Optional[bool]:
        return self._headless

    def provision(self, context: Dict[str, Any]) -> BrowserHandle:
        option = LOCAL_BROWSER_OPTIONS[self._browser_key]
        starting_url = context.get("starting_url") or ""
        nova_kwargs: Dict[str, Any] = {
            "starting_page": starting_url,
            **option.nova_kwargs,
        }
        # Only emit ``headless`` when the caller was explicit — None
        # lets the engine's env-var default win, which keeps CI
        # behaviour unchanged.
        if self._headless is not None:
            nova_kwargs["headless"] = self._headless

        # ``use_default_chrome_browser=True`` has three non-obvious
        # NovaAct requirements we translate for the user:
        #
        # 1. It's macOS-only — NovaAct raises NotImplementedError on
        #    Linux / Windows. Surface that here with a clearer message
        #    rather than letting NovaAct explain.
        # 2. A ``user_data_dir`` must be set explicitly.
        # 3. That dir must NOT be the system default Chrome profile —
        #    NovaAct blocks it for CDP (``_validate_chrome_user_data_dir_ok_for_cdp``)
        #    because running Chrome can't share the profile with the
        #    CDP-automated one.
        #
        # We satisfy (2) + (3) by maintaining a working copy under
        # ``~/.qa-studio/chrome-profile-copy`` and pointing NovaAct at
        # that. The copy is made once; subsequent runs reuse it, so
        # Chrome accumulates state across runs naturally.
        if nova_kwargs.get("use_default_chrome_browser"):
            if sys.platform != "darwin":
                raise RuntimeError(
                    "'Chrome (your profile)' is macOS-only in NovaAct. "
                    "Use 'Chromium' or 'Chrome' instead on this OS."
                )
            nova_kwargs["user_data_dir"] = str(ensure_chrome_profile_copy())

        return BrowserHandle(nova_kwargs=nova_kwargs, teardown=None)
