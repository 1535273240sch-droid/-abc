from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_agent_task_service
from app.schemas.agent import AgentTaskCreate, AgentTaskResponse
from app.services.agent_service import AgentTaskService


router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])


def _actor(request: Request, fallback: str = "admin") -> str:
    user = getattr(request.state, "user", {})
    return str(user.get("sub", fallback)) if isinstance(user, dict) else fallback


@router.get("/tasks", response_model=list[AgentTaskResponse])
async def list_tasks(service: AgentTaskService = Depends(get_agent_task_service)):
    return service.list_tasks()


@router.post("/tasks", response_model=AgentTaskResponse, status_code=201)
async def create_task(body: AgentTaskCreate, request: Request, service: AgentTaskService = Depends(get_agent_task_service)):
    return service.create_task(body.title, body.task_type, _actor(request, body.operator))


@router.post("/tasks/{task_id}/run", response_model=AgentTaskResponse)
async def run_task(task_id: str, request: Request, service: AgentTaskService = Depends(get_agent_task_service)):
    return service.run_task(task_id, _actor(request))
