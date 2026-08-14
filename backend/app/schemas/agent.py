from pydantic import BaseModel, Field


class AgentTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    task_type: str = Field(min_length=1, max_length=64)
    operator: str = "admin"


class AgentTaskResponse(BaseModel):
    task_id: str
    title: str
    task_type: str
    status: str
    operator: str
    started_at: str
    duration: str
    evidence_chain: list[str]
    tool_permissions_used: list[str]
    created_at: str
    updated_at: str
