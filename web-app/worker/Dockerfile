# Worker image for QA Studio: the Lambda MicroVM image.
#
# Lambda builds it from a zip of the .dockerignore-filtered repo root (see
# web-app/lib/worker-image-asset.ts), with this file copied to the zip root,
# so all COPY paths are relative to the repo root.  The image ENTRYPOINT is
# supervisor.py: a stdlib HTTP server that answers the MicroVM lifecycle
# hooks on :8080 and spawns `qa-studio run` (batch) or wizard_worker.py
# (wizard) from the /run payload (.kiro/docs/microvm-runner/design.md).

# ── Build stage ────────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.13.12-slim AS builder

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
# The browser runs remotely via Bedrock AgentCore — no local Playwright
# runtime needed in the image (saves ~300MB).
ENV NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true

RUN apt-get update && \
    apt-get install -y build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install the worker's own runtime deps (nova-act, boto3, etc) plus
# the qa-studio CLI with the [runner,agentcore] extras.  The CLI's
# source lives one level up in the build context, copied in below.
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
FROM public.ecr.aws/docker/library/python:3.13.12-slim

ENV PYTHONUNBUFFERED=1
ENV NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true
# The worker's legacy wizard code expects its module directory on sys.path;
# the supervisor runs its children from WORKER_APP_DIR (/app).
ENV PYTHONPATH=/app
ENV LOGS_DIRECTORY=/app/logs

RUN rm /bin/sh && ln -s /bin/bash /bin/sh && \
    useradd -m -u 1000 worker && \
    mkdir -p /app/logs && \
    chown -R worker:worker /app

# No `aws` CLI or curl in this image.  SSM / Secrets Manager reads happen
# in supervisor.py through boto3 (bundled with the venv).  Keeps the
# image small and the dependency surface honest.

WORKDIR /app
USER worker

# Bring over the pre-built virtualenv and the worker source tree.
# The venv was already built at /app/.venv in the builder stage so
# shebangs match the runtime path — just copy it across.
COPY --from=builder --chown=worker:worker /app/.venv /app/.venv
COPY --chown=worker:worker web-app/worker /app

# Activate the venv for any user shells and make the qa-studio CLI
# resolvable on PATH for the supervisor's children.
ENV PATH="/app/.venv/bin:${PATH}"

ENTRYPOINT ["python", "/app/supervisor.py"]
