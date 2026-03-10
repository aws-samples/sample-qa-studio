# Build stage
FROM python:3.13.12-slim AS builder

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

# Runtime stage
FROM python:3.13.12-slim

ENV PYTHONUNBUFFERED=1
ENV NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true
ENV PYTHONPATH=/app
ENV LOGS_DIRECTORY=/app/logs

RUN rm /bin/sh && ln -s /bin/bash /bin/sh && \
    useradd -m -u 1000 worker && \
    mkdir -p /app/logs && \
    chown -R worker:worker /app

WORKDIR /app
USER worker

COPY --from=builder --chown=worker:worker /app/.venv .venv
COPY --chown=worker:worker . .

CMD ["bash", "-c", "source .venv/bin/activate && python worker.py"]
