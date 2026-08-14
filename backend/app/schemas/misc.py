from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Strategy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    version: str
    kind: str
    status: str
    owner: str
    updatedAt: str
    sharpe: str | None = None
    maxDrawdown: str | None = None
    winRate: str | None = None
    totalReturn: str | None = None
    codeRef: str | None = None
    parameters: dict | None = None


class Backtest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    strategyId: str
    version: str
    timeframe: str | None = None
    initialCapital: str
    netProfit: str
    sharpeRatio: str | None = None
    maxDrawdown: str | None = None
    winRate: str | None = None
    totalTrades: int
    feeModel: str | None = None
    slippageModel: str | None = None
    dataSnapshotId: str | None = None
    createdAt: str
    equityCurve: list[float] | None = None


class AgentTaskSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    type: str
    status: str
    operator: str
    startedAt: str | None = None
    duration: str | None = None
    evidenceChain: list[str] | None = None
    toolPermissionsUsed: list[str] | None = None


class ApprovalSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    type: str
    requestedBy: str
    createdAt: str
    riskLevel: str
    status: str
    details: str | None = None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    eventTime: str
    eventType: str
    actor: str
    module: str
    action: str
    result: str
    traceId: str | None = None
    payload: dict | None = None


class SystemStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    mode: str
    version: str
    uptimeSeconds: int
    services: list[dict]
    market: dict
    eventBus: dict