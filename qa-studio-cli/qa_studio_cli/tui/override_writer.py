"""Tempfile writer for TUI-supplied header / secret runtime overrides.

Writes each non-empty override dict to a mode-``0600`` JSON file in
the platform's tempfile directory, then hands the paths to the caller
for inclusion in ``qa-studio run --headers-file/--secrets-file``.

Empty dicts produce no file so the caller can omit the corresponding
CLI flag. Cleanup is idempotent — the caller is expected to invoke
:func:`cleanup` in a ``finally`` block once the subprocess has ended.

Security posture:

- ``tempfile.mkstemp`` creates the file with ``O_EXCL`` and ``0o600``
  on Unix, closing the race between ``NamedTemporaryFile`` + manual
  ``chmod``.
- Files live under :func:`tempfile.gettempdir` with predictable
  prefixes (``qa-studio-tui-headers-``, ``qa-studio-tui-secrets-``)
  so a user can grep for stragglers if cleanup ever misses.
- Paths are kept in memory on :class:`OverrideFiles`; contents are
  never logged.

See ``.kiro/specs/cli-tui/design.md`` for rationale.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


_HEADERS_PREFIX = "qa-studio-tui-headers-"
_SECRETS_PREFIX = "qa-studio-tui-secrets-"


@dataclass
class OverrideFiles:
    """Paths to the tempfiles the TUI wrote for a run.

    Either attribute may be ``None`` when the caller supplied an
    empty dict, meaning "do not pass the corresponding CLI flag".
    """

    headers_path: Optional[Path] = None
    secrets_path: Optional[Path] = None
    _cleaned: bool = field(default=False, repr=False)

    def paths_to_cleanup(self) -> List[Path]:
        return [p for p in (self.headers_path, self.secrets_path) if p is not None]

    def cleanup(self) -> None:
        """Unlink tempfiles. Safe to call more than once."""
        if self._cleaned:
            return
        for path in self.paths_to_cleanup():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # Best-effort cleanup — a tempfile we can't delete is
                # not worth failing the whole run over.  The ``0o600``
                # mode and short path names make collisions harmless.
                pass
        self._cleaned = True


def _write_json_0600(prefix: str, payload: Dict[str, str]) -> Path:
    """Create a mode-0600 tempfile with the JSON-serialized payload.

    Uses ``os.fdopen`` on the fd returned by ``tempfile.mkstemp`` so
    we never open the path a second time — closes the race where
    another process could swap the inode between creation and write.
    """
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        # If the write fails we still own the fd — close + unlink
        # before propagating so we don't leak a (possibly
        # half-written) file on disk.
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return Path(path)


def write_overrides(
    headers: Dict[str, str],
    secrets: Dict[str, str],
) -> OverrideFiles:
    """Write non-empty override dicts to 0600 tempfiles.

    Args:
        headers: Header name → value override map. Empty dict ⇒ no
            headers tempfile is created and ``headers_path`` is
            ``None``.
        secrets: Secret key → value override map. Empty dict ⇒ no
            secrets tempfile is created and ``secrets_path`` is
            ``None``.

    Returns:
        An :class:`OverrideFiles` instance carrying the paths to any
        files that were created. The caller must invoke
        :meth:`OverrideFiles.cleanup` when the run ends.
    """
    headers_path = _write_json_0600(_HEADERS_PREFIX, headers) if headers else None
    try:
        secrets_path = _write_json_0600(_SECRETS_PREFIX, secrets) if secrets else None
    except Exception:
        # If writing the secrets file failed, unlink the headers file
        # we just created so we don't leave a half-setup run state.
        if headers_path is not None:
            try:
                headers_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return OverrideFiles(headers_path=headers_path, secrets_path=secrets_path)
