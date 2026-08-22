"""GET /api/tasks/{task_id} — task row + its tool calls."""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.core.state import get_state
from backend.memory.retrieval import iso
from backend.services.task_service import TaskService

router = APIRouter(prefix="/api", tags=["tasks"])


def _serialize_task(task) -> dict:
    return {
        "id": task.id,
        "session_id": task.session_id,
        "status": task.status,
        "input": task.input,
        "result": task.result,
        "created_at": iso(task.created_at),
        "completed_at": iso(task.completed_at),
    }


def _serialize_tool_call(row) -> dict:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "tool": row.tool,
        "input": row.input,
        "output": row.output,
        "success": row.success,
        "created_at": iso(row.created_at),
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request) -> dict:
    state = get_state(request)
    tasks = TaskService(state.db.session_factory)
    task, tool_calls = await tasks.get_with_tool_calls(task_id)
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail={"code": "TASK_NOT_FOUND", "message": f"Task not found: {task_id}"},
        )
    return {
        "task": _serialize_task(task),
        "tool_calls": [_serialize_tool_call(row) for row in tool_calls],
    }
