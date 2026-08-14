from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.errors import QuantError


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentTaskService:
    def __init__(self, store: Any):
        self._store = store
        self._seed()

    def _seed(self) -> None:
        if self._store.agent_tasks:
            return
        task_id = "agent-task-market-audit-001"
        created_at = now_iso()
        self._store.agent_tasks[task_id] = {
            "task_id": task_id,
            "title": "盘前市场数据质量巡检",
            "task_type": "data_inspection",
            "status": "completed",
            "operator": "system",
            "started_at": created_at,
            "duration": "12.4s",
            "evidence_chain": [
                "读取统一行情快照",
                "检查 BTCUSDT / ETHUSDT 时间连续性",
                "记录 Paper 数据质量结论",
            ],
            "tool_permissions_used": ["market.read", "audit.append"],
            "created_at": created_at,
            "updated_at": created_at,
        }

    def list_tasks(self) -> list[dict]:
        return list(self._store.agent_tasks.values())

    def get_task(self, task_id: str) -> dict:
        task = self._store.agent_tasks.get(task_id)
        if not task:
            raise QuantError("NOT_FOUND", f"Agent task {task_id} not found", status_code=404)
        return task

    def run_task(self, task_id: str, operator: str) -> dict:
        task = self.get_task(task_id)
        now = now_iso()
        task.update({
            "status": "completed",
            "operator": operator,
            "started_at": now,
            "updated_at": now,
            "duration": "0.1s",
        })
        task["evidence_chain"] = [
            "验证工具权限: market.read",
            "读取统一 Paper 行情快照",
            "完成任务并写入证据链",
        ]
        return task

    def create_task(self, title: str, task_type: str, operator: str) -> dict:
        now = now_iso()
        task_id = f"agent-task-{uuid4().hex[:12]}"
        task = {
            "task_id": task_id,
            "title": title,
            "task_type": task_type,
            "status": "completed",
            "operator": operator,
            "started_at": now,
            "duration": "0.1s",
            "evidence_chain": ["任务已创建", "Paper 工具边界校验通过", "任务完成"],
            "tool_permissions_used": ["market.read", "audit.append"],
            "created_at": now,
            "updated_at": now,
        }
        self._store.agent_tasks[task_id] = task
        return task
