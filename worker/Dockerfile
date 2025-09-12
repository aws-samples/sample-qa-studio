# Use Python 3.11 slim as base image
FROM python:3.13.6-bookworm
# FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true

RUN rm /bin/sh && ln -s /bin/bash /bin/sh

# Install system dependencies required for Nova Act and Chromium
RUN apt-get update && \
    apt-get install -y \
        ca-certificates \
        python3-pip \
        python3-venv \
        python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set up Chrome/Chromium environment
# ENV CHROME_BIN=/usr/bin/chromium
# ENV CHROME_PATH=/usr/bin/chromium
# ENV CHROMIUM_PATH=/usr/bin/chromium
# ENV DISPLAY=:99
# ENV CHROME_DEVEL_SANDBOX=/usr/lib/chromium/chrome-sandbox

# Create a non-root user for security
# RUN useradd -m -u 1000 worker && \
#     mkdir -p /app /app/logs && \
#     chown -R worker:worker /app

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    python3 -m venv .venv && \
    source .venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

# Copy the worker code
COPY . .

# Set ownership of the app directory
# RUN chown -R worker:worker /app

# Switch to non-root user
# USER worker

# Create logs directory
RUN mkdir -p /app/logs

# Set environment variables for the worker
ENV PYTHONPATH=/app
ENV LOGS_DIRECTORY=/app/logs

# Expose any ports if needed (optional)
# EXPOSE 8080

# Default command to run the worker
USER non-root
CMD ["bash", "-c", "source .venv/bin/activate && python worker.py"]
# CMD ["bash", "-c", "python worker.py"]
# CMD ["source .venv/bin/activate && python worker.py"]