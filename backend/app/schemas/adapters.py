from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class AdapterHealthResponse(BaseModel):
    name: str
    status: str
    latency_ms: int
    is_rate_limited: bool
    last_error: str | None = None


class AdapterConnectResponse(BaseModel):
    exchange: str
    status: str
    latency_ms: int
    is_rate_limited: bool
    retry_count: int
    last_checked_at: str


class AdapterSymbolResponse(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    market_type: str
    status: str


class AdapterTickerResponse(BaseModel):
    symbol: str
    source: str
    last_price: str
    bid_price: str
    ask_price: str
    volume_24h: str
    event_time: str
    sequence: int


class CredentialSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    exchange: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_-]+$")
    api_key: str = Field(min_length=8, max_length=256)
    api_secret: str = Field(min_length=8, max_length=256)
    passphrase: str | None = Field(default=None, max_length=256)
    environment: str = Field(default="live", pattern=r"^(live|testnet)$")
    base_url: str | None = Field(default=None, max_length=500)


class CredentialRedactedResponse(BaseModel):
    connection_id: str
    exchange: str
    environment: str | None = None
    base_url: str | None = None
    enabled: bool = False
    credential_status: str
    credential_fingerprint: str | None = None
    has_passphrase: bool = False
    updated_at: datetime | str | None = None


class CredentialTestResponse(BaseModel):
    connection_id: str
    status: str
    message: str
    tested_at: datetime | str | None = None


class LiveDiagnosisResponse(BaseModel):
    account_id: str
    exchange: str | None = None
    authorized: bool
    gates: dict[str, bool]
    blocking_gates: list[str]
    approval_id: str | None = None
    approval_expires_at: str | None = None
    checked_at: str


class LiveAuthorizationRequest(BaseModel):
    account_id: str = "paper-main"
    exchange: str | None = None
    ttl_seconds: int = 86400


class LiveRiskStatusResponse(BaseModel):
    breaker_tripped: bool
    breaker_reason: str | None = None
    breaker_tripped_at: str | None = None
    high_water_mark: str | None = None
    limits: dict[str, float]


class LiveRiskResetRequest(BaseModel):
    operator: str = Field(default="admin", min_length=1, max_length=64)
