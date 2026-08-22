"""Message service: conversation persistence helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.memory import retrieval as repository
from backend.memory.models import Message, Session


class MessageService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create_session(self, title: str = "") -> Session:
        async with self._session_factory() as session:
            return await repository.create_session(session, title=title)

    async def get_session(self, session_id: str) -> Session | None:
        async with self._session_factory() as session:
            return await repository.get_session(session, session_id)

    async def add(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_name: str | None = None,
    ) -> Message:
        async with self._session_factory() as session:
            return await repository.add_message(session, session_id, role, content, tool_name)

    async def history(self, session_id: str, limit: int = 20) -> list[Message]:
        async with self._session_factory() as session:
            return await repository.get_recent_messages(session, session_id, limit)
