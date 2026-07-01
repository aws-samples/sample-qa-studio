"""Unit tests for :mod:`qa_studio_cli.tui.override_writer`.

Pure-Python; no Textual dependency. Runs in any environment.
"""

import json
import os
import stat
from pathlib import Path

from qa_studio_cli.tui.override_writer import (
    OverrideFiles,
    write_overrides,
)


class TestWriteOverrides:
    def test_empty_dicts_produce_no_files(self):
        result = write_overrides({}, {})
        assert result.headers_path is None
        assert result.secrets_path is None
        assert result.paths_to_cleanup() == []

    def test_headers_only_writes_headers_file(self):
        result = write_overrides({"X-Trace": "abc"}, {})
        try:
            assert result.headers_path is not None
            assert result.headers_path.exists()
            assert result.secrets_path is None
            loaded = json.loads(result.headers_path.read_text())
            assert loaded == {"X-Trace": "abc"}
        finally:
            result.cleanup()

    def test_secrets_only_writes_secrets_file(self):
        result = write_overrides({}, {"pw": "s3cr3t"})
        try:
            assert result.secrets_path is not None
            assert result.secrets_path.exists()
            loaded = json.loads(result.secrets_path.read_text())
            assert loaded == {"pw": "s3cr3t"}
        finally:
            result.cleanup()

    def test_both_dicts_produce_two_files(self):
        result = write_overrides({"X": "y"}, {"pw": "v"})
        try:
            assert result.headers_path is not None
            assert result.secrets_path is not None
            assert result.headers_path != result.secrets_path
        finally:
            result.cleanup()

    def test_files_have_0600_permissions(self):
        """Unix only — Windows mkstemp sets permissions differently.

        On Unix systems the mode bits must be exactly ``rw-------``
        so no other user can read the secret tempfile.
        """
        if os.name != "posix":
            return  # skip silently on non-Unix
        result = write_overrides({"X": "y"}, {"pw": "v"})
        try:
            mode = stat.S_IMODE(os.stat(result.secrets_path).st_mode)
            assert mode == 0o600
            mode = stat.S_IMODE(os.stat(result.headers_path).st_mode)
            assert mode == 0o600
        finally:
            result.cleanup()

    def test_predictable_filename_prefixes(self):
        """Users should be able to ``ls /tmp | grep qa-studio-tui-``
        to find leftover override files."""
        result = write_overrides({"X": "y"}, {"pw": "v"})
        try:
            assert result.headers_path.name.startswith("qa-studio-tui-headers-")
            assert result.secrets_path.name.startswith("qa-studio-tui-secrets-")
            assert result.headers_path.suffix == ".json"
            assert result.secrets_path.suffix == ".json"
        finally:
            result.cleanup()


class TestOverrideFilesCleanup:
    def test_cleanup_unlinks_both_files(self):
        result = write_overrides({"X": "y"}, {"pw": "v"})
        headers_path = result.headers_path
        secrets_path = result.secrets_path
        assert headers_path.exists()
        assert secrets_path.exists()

        result.cleanup()

        assert not headers_path.exists()
        assert not secrets_path.exists()

    def test_cleanup_is_idempotent(self):
        result = write_overrides({"X": "y"}, {})
        result.cleanup()
        # Second call must not raise — spec says caller invokes in a
        # finally, may double-call on error paths.
        result.cleanup()

    def test_cleanup_handles_already_missing_file(self):
        """A tempfile deleted by something else must not cause errors."""
        result = write_overrides({"X": "y"}, {})
        result.headers_path.unlink()
        result.cleanup()  # must not raise

    def test_paths_to_cleanup_filters_none(self):
        # Construct directly to exercise the ``None`` branch.
        of = OverrideFiles(headers_path=None, secrets_path=Path("/tmp/x"))
        assert of.paths_to_cleanup() == [Path("/tmp/x")]


class TestFailureAtomicity:
    def test_secrets_write_failure_removes_headers_file(self, monkeypatch):
        """If writing the secrets tempfile fails, the headers
        tempfile must be unlinked too so we don't leave half-setup
        run state."""
        import qa_studio_cli.tui.override_writer as mod

        real_write = mod._write_json_0600
        calls = {"count": 0}

        def flaky(prefix, payload):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("disk full")
            return real_write(prefix, payload)

        monkeypatch.setattr(mod, "_write_json_0600", flaky)

        paths_created: list[Path] = []
        orig = real_write

        def tracking(prefix, payload):
            p = orig(prefix, payload)
            paths_created.append(p)
            return p

        # Second call is the one that blows up; re-wire the mock to
        # track paths from the first successful call.
        calls["count"] = 0
        monkeypatch.setattr(mod, "_write_json_0600", tracking)

        monkeypatch.setattr(mod, "_write_json_0600", lambda prefix, payload:
                            (_ for _ in ()).throw(OSError("disk full"))
                            if prefix == mod._SECRETS_PREFIX
                            else tracking(prefix, payload))

        try:
            mod.write_overrides({"X": "y"}, {"pw": "v"})
            raise AssertionError("expected OSError")
        except OSError:
            pass

        # The one file that was successfully created must have been
        # cleaned up.
        for p in paths_created:
            assert not p.exists(), f"leftover tempfile: {p}"
