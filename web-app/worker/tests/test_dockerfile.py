"""Contract of the worker ``Dockerfile`` (the Lambda MicroVM image).

The image is built by Lambda from a zip of the repo root with the Dockerfile at
the zip root, so the COPY paths are repo-root relative and must not move; the
supervisor is the ENTRYPOINT (``entrypoint.sh`` and ``WORKER_MODE`` are gone).
"""
import json
import re
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parent.parent
DOCKERFILE = WORKER_DIR / "Dockerfile"


def _instructions():
    """``(instruction, argument)`` pairs, comments and blank lines dropped, continuations joined."""
    text = re.sub(r"\\\n", " ", DOCKERFILE.read_text())
    pairs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        instruction, _, argument = line.partition(" ")
        pairs.append((instruction, argument.strip()))
    return pairs


def test_entrypoint_is_the_supervisor():
    entrypoints = [arg for instr, arg in _instructions() if instr == "ENTRYPOINT"]
    assert entrypoints == ['["python", "/app/supervisor.py"]']
    assert json.loads(entrypoints[0]) == ["python", "/app/supervisor.py"]


def test_no_entrypoint_sh_and_no_worker_mode_left():
    text = DOCKERFILE.read_text()
    assert "entrypoint.sh" not in text
    assert "WORKER_MODE" not in text
    assert not (WORKER_DIR / "entrypoint.sh").exists()


def test_copy_paths_are_repo_root_relative_and_unchanged():
    copies = [arg for instr, arg in _instructions() if instr == "COPY"]
    assert copies == [
        "web-app/worker/requirements.txt web-app/worker/requirements.txt",
        "qa-studio-cli qa-studio-cli",
        "--from=builder --chown=worker:worker /app/.venv /app/.venv",
        "--chown=worker:worker web-app/worker /app",
    ]


def test_supervisor_module_is_shipped_at_the_entrypoint_path():
    # COPY web-app/worker /app puts supervisor.py (and supervisor_models.py) at /app
    assert (WORKER_DIR / "supervisor.py").exists()
    assert (WORKER_DIR / "supervisor_models.py").exists()


def test_runtime_stage_keeps_the_venv_on_path_and_runs_as_worker():
    pairs = _instructions()
    envs = [arg for instr, arg in pairs if instr == "ENV"]
    assert 'PATH="/app/.venv/bin:${PATH}"' in envs
    assert "PYTHONPATH=/app" in envs
    assert ("USER", "worker") in pairs
    assert ("WORKDIR", "/app") in pairs
