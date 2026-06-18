# ─────────────────────────────────────────────────────────────────────────────
# Shamrock Trading Bot — Multi-Stage Dockerfile
#
# Stage 1 (builder): Full compiler toolchain to build native wheels
#   - gcc, g++, libssl-dev, pkg-config, Rust (for solders)
#   - All Python packages compiled here into /install
#
# Stage 2 (runtime): Lean image — only compiled wheels + runtime libs
#   - No compiler tools, no build cache, no apt archives
#   - ~60-70% smaller final image vs single-stage
#   - Eliminates "no space left in /var/cache/apt" on VPS rebuilds
#
# Python 3.12 is required for pandas-ta (TA library).
# The bot also runs on Python 3.11 with manual indicator fallbacks in
# strategies/indicators.py — but 3.12 is preferred for full feature support.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install compiler tools needed to build native Python wheels.
# These stay in the builder stage and are NOT copied to the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    git \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (required by solders — Solana Rust SDK)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

# Upgrade pip and install all Python dependencies into /install
# Using --prefix so we can copy the whole directory into the final stage
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt && \
    pip install --no-cache-dir --prefix=/install pandas-ta 2>/dev/null || true

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd -r shamrock && useradd -m -r -g shamrock shamrock

WORKDIR /app

# Install only the minimal runtime shared libraries needed by compiled wheels.
# libssl3 and libgomp1 are runtime-only (no headers, no compiler).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    libgomp1 \
    curl \
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create necessary directories with correct ownership
RUN mkdir -p /app/logs /app/output /app/data && \
    chown -R shamrock:shamrock /app && \
    chmod -R 775 /app/logs /app/output /app/data

# Switch to non-root user
USER shamrock

# Health check: verify bot is actively running (not just importable)
HEALTHCHECK --interval=60s --timeout=15s --start-period=120s --retries=5 \
    CMD python3 -c "\
import json, time; \
f=open('/app/data/dashboard/bot_status.json'); \
d=json.load(f); \
from datetime import datetime, timezone; \
ts_raw=d.get('last_cycle_at') or d.get('timestamp') or d.get('started_at',''); \
ts=datetime.fromisoformat(ts_raw.replace('Z','+00:00')); \
age=(datetime.now(timezone.utc)-ts).total_seconds(); \
print(f'Bot cycle age: {age:.0f}s'); \
exit(0 if age < 900 else 1)" || exit 1

# Default: run the main bot
CMD ["python3", "main.py"]
