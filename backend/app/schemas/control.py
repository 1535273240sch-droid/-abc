from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelProviderUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    display_name: str = Field(min_length=2, max_length=120)
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=160)
    secret_ref: str | None = Field(default=None, max_length=300)
    enabled: bool = False
    capabilities: list[str] = Field(default_factory=list)


class ModelProviderResponse(ModelProviderUpsertRequest):
    status: str
    runtime_ready: bool
    updated_at: datetime
    last_test_at: datetime | None = None
    last_error: str | None = None


class ProviderTestResponse(BaseModel):
    provider_id: str
    status: str
    runtime_ready: bool
    message: str
    tested_at: datetime


class ExchangeConnectionUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    adapter_name: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=2, max_length=120)
    environment: str = Field(default="paper", pattern=r"^(paper|testnet|live)$")
    secret_ref: str | None = Field(default=None, max_length=300)
    enabled: bool = True


class ExchangeConnectionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    connection_id: str
    adapter_name: str
    display_name: str
    environment: str = "paper"
    secret_ref: str | None = None
    enabled: bool = True
    adapter_status: str
    credential_status: str
    latency_ms: int | None = None
    last_error: str | None = None
    updated_at: datetime


class ExchangeTestResponse(BaseModel):
    connection_id: str
    status: str
    runtime_ready: bool
    message: str
    tested_at: datetime
