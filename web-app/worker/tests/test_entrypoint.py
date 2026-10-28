"""Tests for entrypoint.sh (batch mode): the execution capability export (H-2)."""
import os
import stat
import subprocess
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parent.parent / "entrypoint.sh"

FAKE_CLI = """#!/usr/bin/env bash
echo "QA_STUDIO_EXECUTION_TOKEN=${QA_STUDIO_EXECUTION_TOKEN:-<unset>}"
echo "EXECUTION_TOKEN=${EXECUTION_TOKEN:-<unset>}"
echo "ARGS=$*"
"""


@pytest.fixture
def run_entrypoint(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "qa-studio"
    fake.write_text(FAKE_CLI)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    def _run(**overrides):
        env = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "WORKER_MODE": "batch",
            "WORKER_APP_DIR": str(tmp_path),
            "QA_STUDIO_API_URL": "https://api.example.com",
            "OAUTH_TOKEN_ENDPOINT": "https://auth.example.com/oauth2/token",
            "USECASE_ID": "uc-1",
            "EXECUTION_ID": "ex-1",
            "OAUTH_CLIENT_ID": "worker-client",
            "OAUTH_CLIENT_SECRET": "client-secret",
        }
        env.update({k: v for k, v in overrides.items() if v is not None})
        return subprocess.run(["bash", str(ENTRYPOINT)], env=env, capture_output=True, text=True, timeout=30)

    return _run


def test_exports_execution_capability(run_entrypoint):
    result = run_entrypoint(EXECUTION_TOKEN="tok-abc")
    assert result.returncode == 0, result.stderr
    assert "QA_STUDIO_EXECUTION_TOKEN=uc-1:ex-1:tok-abc" in result.stdout
    # The raw token is not passed on as its own variable
    assert "EXECUTION_TOKEN=<unset>" in result.stdout


def test_token_never_logged(run_entrypoint):
    result = run_entrypoint(EXECUTION_TOKEN="tok-very-secret")
    assert "tok-very-secret" not in result.stderr
    assert "tok-very-secret" not in result.stdout.split("ARGS=")[1]


def test_missing_token_warns_and_runs_without_capability(run_entrypoint):
    result = run_entrypoint()
    assert result.returncode == 0, result.stderr
    assert "QA_STUDIO_EXECUTION_TOKEN=<unset>" in result.stdout
    assert "EXECUTION_TOKEN not set" in result.stderr
