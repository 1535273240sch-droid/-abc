from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SystemStatusResponse(BaseModel):
    app_name: str
    app_version: str
    mode: str
    uptime_seconds: float
    status: str = "running"
    timestamp: datetime = Field(default_factory=datetime.utcnow)