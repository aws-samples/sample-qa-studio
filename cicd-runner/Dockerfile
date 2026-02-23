# ── Stage 1: Builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true

RUN apt-get update && \
    apt-get install -y build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN python3 -m venv .venv && \
    .venv/bin/pip install --no-cache-dir --upgrade pip && \
    .venv/bin/pip install --no-cache-dir -r requirements.txt

COPY setup.py .
COPY src/ src/

RUN .venv/bin/pip install --no-cache-dir .

# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true
ENV PYTHONPATH=/app

WORKDIR /app

# Create non-root runner user (uid 1000)
RUN useradd -m -u 1000 runner

# Install Playwright Chromium + OS deps, move cache to runner user,
# then clean up root cache and system playwright package in one layer
RUN pip install --no-cache-dir playwright && \
    python -m playwright install --with-deps chromium && \
    mkdir -p /home/runner/.cache && \
    cp -r /root/.cache/ms-playwright /home/runner/.cache/ && \
    chown -R runner:runner /home/runner/.cache && \
    rm -rf /root/.cache/ms-playwright && \
    rm -rf /home/runner/.cache/ms-playwright/chromium_headless_shell-* && \
    rm -rf /home/runner/.cache/ms-playwright/ffmpeg-* && \
    pip uninstall -y playwright && \
    rm -rf /var/lib/apt/lists/*

# Copy venv from builder stage
COPY --from=builder --chown=runner:runner /app/.venv /app/.venv

# Create logs directory with runner ownership
RUN mkdir -p /app/logs && chown -R runner:runner /app

# Add venv to PATH so cicd-runner is available
ENV PATH="/app/.venv/bin:$PATH"

USER runner

ENTRYPOINT ["/app/.venv/bin/cicd-runner"]
