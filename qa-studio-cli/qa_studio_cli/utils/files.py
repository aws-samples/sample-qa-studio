"""Filesystem helpers for files whose names come from untrusted sources."""

import re
from pathlib import Path

DEFAULT_DOWNLOAD_NAME = "download"
_MAX_NAME_LENGTH = 255
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def safe_download_filename(name: str | None) -> str:
    """Reduce a server- or page-supplied filename to a safe basename.

    Download filenames come from the site under test (Content-Disposition
    header, URL path, or the browser's suggested name), so they must never be
    used as a path: strip any directory components (``/`` and ``\\``), control
    characters and leading dots, so ``../../etc/passwd`` becomes ``passwd``.
    """
    base = re.split(r"[\\/]", name or "")[-1]
    base = _CONTROL_CHARS.sub("", base).strip().lstrip(".").strip()
    return base[:_MAX_NAME_LENGTH] or DEFAULT_DOWNLOAD_NAME


def path_in_directory(directory: str | Path, name: str | None) -> str:
    """Return ``directory/<safe name>``, guaranteed to stay inside ``directory``."""
    root = Path(directory).resolve()
    candidate = (root / safe_download_filename(name)).resolve()
    if candidate.parent != root:
        raise ValueError("Download filename resolves outside the download directory")
    return str(candidate)
