# Enterprise AI Quant System

[![CI/CD](https://github.com/your-org/quant-system/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/quant-system/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Production-grade quantitative trading platform with enterprise architecture, risk controls, and observability built in.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Observability](#observability)
- [Security](#security)
- [Development](#development)

---

## Overview

The Enterprise AI Quant System is a full-stack quantitative trading platform that provides:

- **Order lifecycle management** — risk preflight → order creation → execution → fill accounting → position update
- **Risk controls** — max notional, positive quantity, min quantity, market quality gate, kill switch
- **Strategy engine** — pluggable strategy engines (trend, arbitrage, grid) with a registry pattern
- **Reconciliation** — position vs. order consistency checks with resolution workflow
- **Governance** — approval workflow, kill switch recovery, audit trail
- **Paper trading** — simulated exchange adapter with realistic fill mechanics

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `Decimal` everywhere | Financial calculations must never use floating-point |
| In-memory + DB dual store | Fast reads from memory; durability from PostgreSQL |
| Event-driven | Domain events published on every state change |
| RBAC | 4 roles: viewer, quant, risk_officer, admin |
| Paper-only by default | Live trading blocked until production validation |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Nginx (TLS)                          │
│                  Rate Limit + Reverse Proxy                 │
└───────────────┬───────────────────────────┬────────────────┘
                │                           │
┌───────────────▼───────────┐  ┌────────────▼───────────────┐
│     FastAPI Application    │  │    Celery Worker           │
│  (gunicorn + uvicorn x4)   │  │  (strategy scheduler,     │
│                            │  │   market refresh, recon)   │
│  ┌──────────────────────┐  │  └──────────────────────────┘
│  │   API Layer (v1)     │  │
│  │  20+ route modules   │  │
│  ├──────────────────────┤  │
│  │   Service Layer       │  │
│  │  OrderService         │  │
│  │  RiskService          │  │
│  │  PositionService      │  │
│  │  StrategyRuntime      │  │
│  │  KillSwitchService    │  │
│  │  Reconciliation       │  │
│  │  ApprovalService      │  │
│  │  AuditService         │  │
│  │  MarketService        │  │
│  ├──────────────────────┤  │
│  │   Persistence Layer   │  │
│  │  InMemoryStore /      │  │
│  │  DBStore (SQLAlchemy)  │  │
│  ├──────────────────────┤  │
│  │   Event Bus           │  │
│  │  Memory / Redis Streams│ │
│  ├──────────────────────┤  │
│  │   Adapter Layer        │  │
│  │  PaperExchangeAdapter │  │
│  │  RateLimiter           │  │
│  │  ConnectionManager     │  │
│  └──────────────────────┘  │
└───────────┬───────────────┘
            │
    ┌───────┴───────┐
    │               │
┌───▼───┐    ┌──────▼──────┐
│Redis  │    │ PostgreSQL  │
│Events │    │  20 tables  │
│Cache  │    │  Alembic    │
│Locks  │    │  Migrations │
└───────┘    └─────────────┘
```

### Project Structure

```
.
├── app/
│   ├── main.py                    # FastAPI app, middleware, lifespan
│   ├── core/
│   │   ├── config.py              # Settings + production validation
│   │   ├── auth.py                # JWT + RBAC
│   │   ├── api_key.py             # API Key generation/verification
│   │   ├── rate_limit.py          # Token-bucket rate limiter
│   │   ├── distributed_lock.py    # Redis distributed lock
│   │   ├── logging.py             # Structured JSON logging
│   │   ├── network.py             # SSRF protection
│   │   ├── errors.py              # QuantError + error response
│   │   └── secrets.py             # Secret management
│   ├── db/
│   │   ├── memory.py              # InMemoryStore (dev/test)
│   │   ├── db_store.py             # DBStore (production)
│   │   ├── database.py             # Engine + session management
│   │   └── orm_models.py           # SQLAlchemy ORM models (20 tables)
│   ├── services/                  # Business logic (15+ services)
│   ├── adapters/                   # Exchange adapters
│   ├── api/v1/                     # API route handlers (20+ modules)
│   ├── models/                     # Domain models + enums
│   ├── schemas/                    # Pydantic request/response schemas
│   ├── events/bus.py               # Event bus (memory + Redis Streams)
│   ├── observability/
│   │   ├── metrics.py              # Prometheus metrics
│   │   ├── tracing.py              # OpenTelemetry tracing
│   │   └── health.py               # Liveness/readiness probes
│   └── tasks/                      # Celery async tasks
│       ├── celery_app.py
│       └── tasks.py
├── alembic/                        # Database migrations
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py
├── tests/                          # 250+ unit tests
├── deploy/
│   └── nginx.conf                  # Nginx reverse proxy config
├── Dockerfile                      # Multi-stage build
├── docker-compose.yml              # Full stack: app + worker + beat + pg + redis + nginx
├── .github/workflows/ci.yml        # CI/CD pipeline
├── .env.example                    # Environment template
├── requirements.txt
└── alembic.ini
```

---

## Quick Start

### Using Docker Compose (recommended)

```bash
# 1. Copy environment template
cp .env.example .env
# Edit .env with your secrets (auth secret, admin password, etc.)

# 2. Generate TLS certificates (or use Let's Encrypt in production)
mkdir -p deploy/certs
openssl req -x509 -newkey rsa:4096 -keyout deploy/certs/key.pem \
  -out deploy/certs/cert.pem -days 365 -nodes -subj "/CN=localhost"

# 3. Start the full stack
docker compose up -d

# 4. Run database migrations
docker compose exec app alembic upgrade head

# 5. Verify
curl https://localhost/health/ready
```

### Local Development

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export QUANT_ENVIRONMENT=development
export QUANT_AUTH_ENABLED=false
export QUANT_STORAGE_ENABLED=false
export QUANT_DEBUG=true

# 4. Run the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Run tests
pytest tests/ -v

# 6. Open API docs
# Visit http://localhost:8000/docs
```

---

## Configuration

All configuration is via environment variables (prefix `QUANT_`) or a `.env` file.

### Key Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `QUANT_ENVIRONMENT` | `development` | `development` or `production` |
| `QUANT_MODE` | `paper` | `paper` or `live` (live blocked in dev) |
| `QUANT_AUTH_ENABLED` | `false` | Enable JWT + API Key authentication |
| `QUANT_AUTH_SECRET` | `""` | HMAC signing secret (≥32 chars in prod) |
| `QUANT_STORAGE_BACKEND` | `pickle` | `pickle` or `postgres` |
| `QUANT_POSTGRES_DSN` | `""` | PostgreSQL connection string |
| `QUANT_REDIS_URL` | `""` | Redis connection string |
| `QUANT_EVENT_BACKEND` | `memory` | `memory` or `redis` |
| `QUANT_LOG_FORMAT` | `json` | `json` or `text` |
| `QUANT_RATE_LIMIT_ENABLED` | `true` | Enable API rate limiting |
| `QUANT_RATE_LIMIT_RPM` | `120` | Requests per minute per client |
| `QUANT_OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `QUANT_SENTRY_DSN` | `""` | Sentry error tracking DSN |
| `QUANT_ENABLE_CELERY` | `false` | Enable Celery async tasks |

See [`.env.example`](.env.example) for the full list.

---

## Deployment

### Docker Compose

The `docker-compose.yml` file defines 6 services:

| Service | Description | Port |
|---------|-------------|------|
| `app` | FastAPI application (4 workers) | 8000 (internal) |
| `worker` | Celery worker (async tasks) | — |
| `beat` | Celery beat (scheduled tasks) | — |
| `postgres` | PostgreSQL 16 | 5432 |
| `redis` | Redis 7 (events + cache + broker) | 6379 |
| `nginx` | Nginx reverse proxy (TLS) | 80, 443 |

### Production Checklist

Before deploying to production:

- [ ] Set `QUANT_ENVIRONMENT=production`
- [ ] Set `QUANT_AUTH_ENABLED=true`
- [ ] Set `QUANT_AUTH_SECRET` to a 32+ character random string
- [ ] Set `QUANT_AUTH_ADMIN_PASSWORD` to a 12+ character password
- [ ] Set `QUANT_STORAGE_BACKEND=postgres` with a proper DSN
- [ ] Set `QUANT_EVENT_BACKEND=redis` with a proper Redis URL
- [ ] Set `QUANT_CORS_ORIGINS` to explicit allowed origins
- [ ] Set `QUANT_ALLOWED_HOSTS` to explicit allowed hosts
- [ ] Configure TLS certificates for Nginx
- [ ] Set up database backups (pg_dump cron job)
- [ ] Configure Sentry DSN (optional but recommended)
- [ ] Configure OpenTelemetry collector (optional)

---

## API Documentation

When the application is running, interactive API documentation is available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/login` | Authenticate and get JWT token |
| `GET` | `/api/v1/auth/status` | Check auth configuration |
| `POST` | `/api/v1/risk/preflight` | Run risk pre-check |
| `POST` | `/api/v1/orders` | Create order intent |
| `GET` | `/api/v1/orders` | List orders |
| `POST` | `/api/v1/execution/{id}/fill` | Fill an order |
| `POST` | `/api/v1/execution/{id}/cancel` | Cancel an order |
| `GET` | `/api/v1/positions` | List positions |
| `POST` | `/api/v1/strategies` | Create strategy |
| `GET` | `/api/v1/strategies` | List strategies |
| `POST` | `/api/v1/governance/approvals` | Create approval |
| `POST` | `/api/v1/governance/kill-switch/trigger` | Trigger kill switch |
| `POST` | `/api/v1/reconciliation` | Run reconciliation |
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/metrics` | Prometheus metrics |

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html

# Run specific test file
pytest tests/test_api.py -v

# Run with parallel execution
pytest tests/ -v -n 4
```

### Test Structure

| File | Description |
|------|-------------|
| `test_api.py` | API endpoint integration tests |
| `test_trading_logic_fixes.py` | Critical trading bug fix tests |
| `test_p2_improvements.py` | P2 improvement tests (auth, RBAC, SSRF, etc.) |
| `test_persistence.py` | Store persistence tests |
| `test_fixes.py` | General bug fix tests |

---

## Observability

### Logging

Structured JSON logging is enabled by default. All log entries include:
- Timestamp (ISO 8601, UTC)
- Request ID (correlated across the request lifecycle)
- Log level
- Logger name
- Message + structured fields

Example log entry:
```json
{
  "timestamp": "2025-01-01T12:00:00.000Z",
  "level": "INFO",
  "logger": "app.main",
  "message": "application starting",
  "request_id": "abc-123",
  "version": "0.2.0",
  "environment": "production"
}
```

### Metrics

Prometheus-format metrics at `/metrics`:
- `quant_http_requests_total` — request count by method/path/status
- `quant_http_latency_ms_total` — cumulative request latency

### Tracing

OpenTelemetry distributed tracing (optional):
- HTTP request spans
- Database query spans
- Redis operation spans

Configure via:
```
QUANT_OTEL_ENABLED=true
QUANT_OTEL_ENDPOINT=http://otel-collector:4317
```

### Health Checks

| Endpoint | Purpose | Docker `HEALTHCHECK` |
|----------|---------|----------------------|
| `/health` | Liveness (process alive?) | ✅ |
| `/health/ready` | Readiness (dependencies ready?) | — |
| `/health/info` | System info (version, uptime) | — |

### Sentry

Error tracking with Sentry:
```
QUANT_SENTRY_DSN=https://xxx@sentry.io/xxx
```

---

## Security

### Authentication

Two authentication methods:

1. **JWT Bearer Token** — Standard HMAC-SHA256 signed tokens (1 hour TTL)
2. **API Key** — Long-lived HMAC-signed keys for automated clients (format: `qak.<id>.<body>.<sig>`)

### RBAC Roles

| Role | Permissions |
|------|------------|
| `viewer` | Read-only (GET) |
| `quant` | Read + write orders/strategies |
| `risk_officer` | Read + governance |
| `admin` | Full access |

### Security Headers

All responses include:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Strict-Transport-Security` (when HTTPS is forced)

### Rate Limiting

- Token-bucket algorithm (in-memory or Redis-backed)
- Default: 120 RPM per client, burst 20
- Nginx-level rate limiting (30 r/s for API, 5 r/s for auth)

### SSRF Protection

Market data fetching validates URLs against:
- Private IP ranges (10.x, 172.16-31.x, 192.168.x)
- Loopback addresses
- Link-local addresses

---

## Development

### Code Quality

```bash
# Lint
ruff check app/

# Format
ruff format app/

# Type check
mypy app/ --ignore-missing-imports

# Security scan
bandit -r app/
pip-audit
```

### Database Migrations

```bash
# Generate migration after model changes
alembic revision --autogenerate -m "description of change"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current version
alembic current
```

### Adding a New Strategy Engine

```python
from app.services.strategy_engines import StrategyEngine, StrategyEngineRegistry

class MyEngine(StrategyEngine):
    def generate_signals(self, strategy, quality, tickers):
        # ... your signal logic ...
        return [{"symbol": "BTCUSDT", "action": "buy", "quantity": "0.01"}]

# Register it
registry = StrategyEngineRegistry()
registry.register("my_kind", MyEngine())
```

---

## License

MIT License — see [LICENSE](LICENSE) file for details.
