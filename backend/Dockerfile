# ─── Stage 1: Build / install dependencies ────────────────────────
FROM python:3.12-slim AS builder

# Set build-time env to avoid .pyc caching and writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (better Docker layer caching)
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --user --no-cache-dir -r requirements.txt && \
    pip install --user --no-cache-dir psycopg[binary] sqlalchemy alembic \
        redis structlog opentelemetry-api opentelemetry-sdk \
        opentelemetry-instrumentation-fastapi \
        opentelemetry-exporter-otlp \
        sentry-sdk

# ─── Stage 2: Runtime image ───────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Enterprise AI Quant System" \
      org.opencontainers.image.description="Production-grade quantitative trading platform" \
      org.opencontainers.image.version="0.2.0" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:${PATH}" \
    QUANT_ENVIRONMENT=production

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r quant && useradd -r -g quant -d /app -s /sbin/nologin quant

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY --chown=quant:quant . .

# Create data directory
RUN mkdir -p /app/.data && chown quant:quant /app/.data

# Switch to non-root user
USER quant

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn via gunicorn for production
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
