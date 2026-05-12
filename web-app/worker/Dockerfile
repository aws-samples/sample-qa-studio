# Worker image for QA Studio.
#
# Docker build context is the repo root (see web-app/lib/worker-stack.ts:
# DockerImageAsset.directory = ".."), so all COPY paths are relative to
# the repo root.  The entrypoint script translates the ECS-provided env
# vars into `qa-studio run` flags for batch mode; wizard mode still
# invokes wizard_worker.py directly until the wizard migration
# (follow-up spec).

# ── Build stage ────────────────────────────────────────────────────
FROM python:3.13.12-slim AS builder

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
# The browser runs remotely via Bedrock AgentCore — no local Playwright
# runtime needed in the container (saves ~300MB).
ENV NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true

RUN apt-get update && \
    apt-get install -y build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install the worker's own runtime deps (nova-act, boto3, etc) plus
# the qa-studio CLI with the [runner,agentcore] extras.  The CLI's
# source lives one level up in the Docker build context, copied in
# below.
#
# IMPORTANT: The venv is created at /app/.venv — the same path it will
# occupy in the runtime stage.  Console-script shebangs (e.g.
# #!/app/.venv/bin/python3) are baked in at install time, so the build
# path must match the final path.  Creating at /build/.venv and copying
# to /app/.venv leaves stale shebangs that cause "required file not
# found" at runtime.
COPY web-app/worker/requirements.txt web-app/worker/requirements.txt
COPY qa-studio-cli qa-studio-cli

RUN python3 -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir --upgrade pip && \
    /app/.venv/bin/pip install --no-cache-dir -r web-app/worker/requirements.txt && \
    /app/.venv/bin/pip install --no-cache-dir "/build/qa-studio-cli[runner,agentcore]"

# ── Runtime stage ──────────────────────────────────────────────────
FROM python:3.13.12-slim

ENV PYTHONUNBUFFERED=1
ENV NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true
# The worker's legacy code expects its module directory on sys.path;
# the entrypoint `cd`s into it before invoking Python.
ENV PYTHONPATH=/app
ENV LOGS_DIRECTORY=/app/logs

RUN rm /bin/sh && ln -s /bin/bash /bin/sh && \
    useradd -m -u 1000 worker && \
    mkdir -p /app/logs && \
    chown -R worker:worker /app

# No `aws` CLI or curl in this image.  SSM reads from the entrypoint
# go through boto3 (bundled with the venv); any other AWS calls run
# via the Python runtime.  Keeps the image small and the dependency
# surface honest.

WORKDIR /app
USER worker

# Bring over the pre-built virtualenv and the worker source tree.
# The venv was already built at /app/.venv in the builder stage so
# shebangs match the runtime path — just copy it across.
COPY --from=builder --chown=worker:worker /app/.venv /app/.venv
COPY --chown=worker:worker web-app/worker /app

# Ensure the entrypoint is executable (COPY preserves mode, but on
# systems where the file is checked out without +x this is a safety
# net).
RUN chmod +x /app/entrypoint.sh

# Activate the venv for any user shells and make the qa-studio CLI
# resolvable on PATH at container start.
ENV PATH="/app/.venv/bin:${PATH}"

ENTRYPOINT ["/app/entrypoint.sh"]
