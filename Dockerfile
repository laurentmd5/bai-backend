# =============================================================================
# BARROW.AI POC - Dockerfile
# Multi-stage build for optimized production image
# =============================================================================

# =============================================================================
# STAGE 1: Builder
# =============================================================================
FROM python:3.13-slim-bookworm AS builder

# Set build environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# =============================================================================
# STAGE 2: Runtime
# =============================================================================
FROM python:3.13-slim-bookworm AS runtime

# Set runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_HOME=/app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd -r barrowai && \
    useradd -r -g barrowai -d $APP_HOME -s /sbin/nologin barrowai

# Copy virtual environment from builder
COPY --from=builder --chown=barrowai:barrowai /opt/venv /opt/venv

# Create application directories
RUN mkdir -p $APP_HOME/app \
    $APP_HOME/logs \
    $APP_HOME/uploads \
    $APP_HOME/data \
    && chown -R barrowai:barrowai $APP_HOME

# Switch to non-root user
USER barrowai
WORKDIR $APP_HOME

# Copy application code
COPY --chown=barrowai:barrowai . $APP_HOME

# Create __init__.py files if they don't exist
RUN find $APP_HOME/app -type d -exec touch {}/__init__.py \; 2>/dev/null || true

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--loop", "uvloop", "--http", "httptools", "--proxy-headers", "--forwarded-allow-ips", "*"]