"""Notification service: persists user-facing notifications (e.g. approval
requests, task failures) that the dashboard can surface as toasts."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.memory import retrieval as repository
from backend.memory.models import Notification


class NotificationService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create(self, level: str, title: str, body: str = "") -> Notification:
        async with self._session_factory() as session:
            return await repository.add_notification(session, level, title, body)

    async def unread(self) -> list[Notification]:
        async with self._session_factory() as session:
            return await repository.get_unread_notifications(session)
