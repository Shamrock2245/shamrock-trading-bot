# ─────────────────────────────────────────────────────────────────────────────
# Shamrock Trading Bot — Dockerfile
# Multi-stage build: lean production image
#
# Python 3.12 is required for pandas-ta (TA library).
# The bot also runs on Python 3.11 with manual indicator fallbacks in
# strategies/indicators.py — but 3.12 is preferred for full feature support.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

# Security: run as non-root user
RUN groupadd -r shamrock && useradd -m -r -g shamrock shamrock

WORKDIR /app

# Install system dependencies
# gcc/g++ needed for web3, solders (Rust-based), and numba (pandas-ta dependency)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    git \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pandas-ta  # Python 3.12+ only — installs cleanly here

# Copy application code
COPY . .

# Create necessary directories with correct ownership
RUN mkdir -p /app/logs /app/output /app/data && \
    chown -R shamrock:shamrock /app && \
    chmod -R 755 /app/logs /app/output

# Switch to non-root user
USER shamrock

# Health check: verify bot is actively running (not just importable)
HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=3 \
    CMD python3 -c "\
import json, time; \
f=open('/app/data/dashboard/bot_status.json'); \
d=json.load(f); \
from datetime import datetime, timezone; \
ts_raw=d.get('last_cycle_at') or d.get('timestamp') or d.get('started_at',''); \
ts=datetime.fromisoformat(ts_raw.replace('Z','+00:00')); \
age=(datetime.now(timezone.utc)-ts).total_seconds(); \
print(f'Bot cycle age: {age:.0f}s'); \
exit(0 if age < 300 else 1)" || exit 1

# Default: run the main bot
CMD ["python3", "main.py"]
