# ─────────────────────────────────────────────────────────────────────────────
# Shamrock Trading Bot — Dockerfile
# Multi-stage build: lean production image
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Security: run as non-root user
RUN groupadd -r shamrock && useradd -r -g shamrock shamrock

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories with correct ownership
RUN mkdir -p /app/logs /app/output /app/data && \
    chown -R shamrock:shamrock /app && \
    chmod -R 755 /app/logs /app/output

# Switch to non-root user
USER shamrock

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)" || exit 1

# Default: run the main bot
CMD ["python3", "main.py"]
