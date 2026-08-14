from datetime import datetime

from pydantic import BaseModel, Field


class StrategyCreateRequest(BaseModel):
    strategy_id: str
    name: str
    version: str
    description: str = ""
    parameters: dict | None = None
    code_ref: str | None = None
    owner: str | None = None
    kind: str | None = None


class StrategyUpdateRequest(BaseModel):
    name: str | None = None
    version: str | None = None
    description: str | None = None
    parameters: dict | None = None
    code_ref: str | None = None
    owner: str | None = None
    kind: str | None = None
    status: str | None = None


class StrategyResponse(BaseModel):
    strategy_id: str
    name: str
    version: str
    description: str
    parameters: dict
    code_ref: str | None = None
    owner: str | None = None
    kind: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime