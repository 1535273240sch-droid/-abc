from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = Field(min_length=2, max_length=64)
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class ChatResponse(BaseModel):
    provider_id: str
    model: str
    content: str
    usage: dict
    latency_ms: int
    status: str
