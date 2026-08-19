from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Enterprise AI Quant System"
    app_version: str = "0.1.0"
    environment: str = "development"
    mode: str = "paper"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    allowed_hosts: list[str] = ["*"]
    force_https: bool = False
    storage_enabled: bool = False
    storage_path: str = ".data/quant-store.pkl"
    storage_backend: str = "pickle"
    storage_migration_source: str = ""
    postgres_dsn: str = ""
    market_data_mode: str = "public"
    market_refresh_seconds: int = 15
    metrics_enabled: bool = True
    metrics_auth_enabled: bool = True
    auth_enabled: bool = False
    auth_secret: str = ""
    auth_admin_username: str = "admin"
    auth_admin_password: str = ""
    auth_token_ttl_seconds: int = 3600
    strategy_scheduler_enabled: bool = False
    strategy_scheduler_interval_seconds: int = 300
    event_backend: str = "memory"
    redis_url: str = ""
    event_stream: str = "quant.domain.events"

    # ── Enterprise infrastructure settings ──
    log_level: str = "INFO"
    log_format: str = "json"          # "json" or "text"
    log_file: str = ""               # empty = stdout only
    otel_enabled: bool = False
    otel_endpoint: str = ""          # OTLP collector URL
    otel_service_name: str = "quant-system"
    rate_limit_enabled: bool = True
    rate_limit_rpm: int = 120         # requests per minute per API key
    rate_limit_burst: int = 20
    api_key_enabled: bool = False
    database_echo: bool = False       # SQL query logging
    enable_celery: bool = False
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    sentry_dsn: str = ""             # Sentry error tracking

    # ── Live trading (P2-1) ──
    # Master switch for real-money order submission. Requires ALL of:
    # this flag + an approved live_switch governance approval + configured
    # exchange credentials (see LiveModeService).
    live_trading_enabled: bool = False
    # Master key for sealing exchange credentials at rest (>=16 chars).
    secrets_master_key: str = ""
    # Live risk limits (LiveRiskService)
    live_max_position_pct: float = 0.25   # max single-symbol exposure / equity
    live_max_drawdown_pct: float = 0.10   # equity drawdown from HWM before breaker

    # ── Backtest engine (P2-2) ──
    backtest_max_bars: int = 50000        # hard cap on bars per run
    backtest_max_optimization_runs: int = 200

    model_config = {"env_prefix": "QUANT_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


def validate_runtime_settings() -> None:
    """Fail fast when a production deployment is missing a safety control."""
    if settings.environment.lower() not in {"production", "prod"}:
        return

    problems: list[str] = []
    if settings.debug:
        problems.append("QUANT_DEBUG must be false in production")
    if settings.mode == "live" and not settings.live_trading_enabled:
        problems.append("live mode requires QUANT_LIVE_TRADING_ENABLED=true")
    if not settings.auth_enabled:
        problems.append("QUANT_AUTH_ENABLED must be true in production")
    if len(settings.auth_secret) < 32:
        problems.append("QUANT_AUTH_SECRET must be at least 32 characters")
    if len(settings.auth_admin_password) < 12:
        problems.append("QUANT_AUTH_ADMIN_PASSWORD must be at least 12 characters")
    if not settings.storage_enabled:
        problems.append("QUANT_STORAGE_ENABLED must be true in production")
    if settings.storage_backend == "postgres" and not settings.postgres_dsn:
        problems.append("QUANT_POSTGRES_DSN is required when QUANT_STORAGE_BACKEND=postgres")
    if settings.event_backend == "redis" and not settings.redis_url:
        problems.append("QUANT_REDIS_URL is required when QUANT_EVENT_BACKEND=redis")
    if not settings.cors_origins or "*" in settings.cors_origins:
        problems.append("QUANT_CORS_ORIGINS must be an explicit allow-list")
    if not settings.allowed_hosts or "*" in settings.allowed_hosts:
        problems.append("QUANT_ALLOWED_HOSTS must be an explicit allow-list")
    if settings.rate_limit_enabled and settings.rate_limit_rpm <= 0:
        problems.append("QUANT_RATE_LIMIT_RPM must be positive")
    if settings.sentry_dsn and not settings.sentry_dsn.startswith("http"):
        problems.append("QUANT_SENTRY_DSN must be a valid HTTP(S) URL")
    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))
