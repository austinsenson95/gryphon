"""Event bus: the single funnel for all system events.

Every ``publish()``:
  1. persists the event to the DB ``events`` table, then
  2. broadcasts it to all connected /ws clients, then
  3. notifies in-process subscribers (used by tests and internal services).

Persistence happens BEFORE broadcast so the events table is always the
complete, ordered source of truth.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.logging import get_logger
from backend.memory import retrieval as repository
from backend.events.events import EventEnvelope
from backend.events.websocket_manager import WebSocketManager

logger = get_logger("griffin.events")

Subscriber = Callable[[EventEnvelope], Awaitable[None] | None]


class EventBus:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        ws_manager: WebSocketManager,
    ) -> None:
        self._session_factory = session_factory
        self._ws_manager = ws_manager
        self._subscribers: list[Subscriber] = []

    def subscribe(self, callback: Subscriber) -> None:
        """Register a sync or async callback invoked for every published event."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def publish(self, event: EventEnvelope) -> EventEnvelope:
        async with self._session_factory() as session:
            await repository.add_event(
                session,
                event_id=event.id,
                type=event.type,
                session_id=event.session_id,
                task_id=event.task_id,
                run_id=event.run_id,
                data=event.data,
            )
        logger.debug(
            "events.published",
            extra={"event_type": event.type, "event_id": event.id},
        )
        await self._ws_manager.broadcast(event)
        for subscriber in list(self._subscribers):
            result = subscriber(event)
            if inspect.isawaitable(result):
                await result
        return event
