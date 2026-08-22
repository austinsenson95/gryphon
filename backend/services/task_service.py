"""Task service: task lifecycle helpers on top of the repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.memory import retrieval as repository
from backend.memory.models import Task


class TaskService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create(self, session_id: str, input_text: str) -> Task:
        async with self._session_factory() as session:
            return await repository.create_task(session, session_id, input_text)

    async def mark_running(self, task_id: str) -> None:
        async with self._session_factory() as session:
            await repository.set_task_status(session, task_id, "running")

    async def complete(self, task_id: str, result: str) -> None:
        async with self._session_factory() as session:
            await repository.set_task_status(
                session, task_id, "completed", result=result, completed=True
            )

    async def fail(self, task_id: str, error: str) -> None:
        async with self._session_factory() as session:
            await repository.set_task_status(
                session, task_id, "failed", result=error, completed=True
            )

    async def get(self, task_id: str) -> Task | None:
        async with self._session_factory() as session:
            return await repository.get_task(session, task_id)

    async def get_with_tool_calls(self, task_id: str) -> tuple[Task | None, list]:
        async with self._session_factory() as session:
            task = await repository.get_task(session, task_id)
            tool_calls = await repository.get_tool_calls_for_task(session, task_id)
            return task, tool_calls
