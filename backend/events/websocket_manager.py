"""WebSocket connection manager.

Tracks connected /ws clients, broadcasts event envelopes to all of them
(tolerating client drops), and on connect sends a ``CONNECTED`` hello followed
by a replay of the most recent 20 events so late-joining dashboards catch up.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket

from backend.core.logging import get_logger
from backend.events.events import EventEnvelope, utc_iso_now

logger = get_logger("gryphon.ws")

REPLAY_LIMIT = 20

# Async callable returning the most recent persisted event envelopes.
HistoryProvider = Callable[[int], Awaitable[list[EventEnvelope]]]


class WebSocketManager:
    def __init__(self, history_provider: HistoryProvider | None = None) -> None:
        self._connections: set[WebSocket] = set()
        self._history_provider = history_provider

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("ws.client_connected", extra={"clients": len(self._connections)})
        await self._send_hello(websocket)
        await self._replay_history(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        logger.info("ws.client_disconnected", extra={"clients": len(self._connections)})

    async def broadcast(self, event: EventEnvelope) -> None:
        """Send an event to every connected client; drop dead connections."""
        if not self._connections:
            return
        payload = event.model_dump()
        dead: list[WebSocket] = []
        for websocket in list(self._connections):
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.warning("ws.broadcast_drop", extra={"error": str(exc)[:200]})
                dead.append(websocket)
        for websocket in dead:
            self._connections.discard(websocket)

    async def _send_hello(self, websocket: WebSocket) -> None:
        await websocket.send_json(
            {
                "type": "CONNECTED",
                "message": "Connected to Gryphon event stream",
                "timestamp": utc_iso_now(),
            }
        )

    async def _replay_history(self, websocket: WebSocket) -> None:
        if self._history_provider is None:
            return
        try:
            recent = await self._history_provider(REPLAY_LIMIT)
        except Exception as exc:
            logger.warning("ws.replay_failed", extra={"error": str(exc)[:200]})
            return
        for event in recent:
            payload: dict[str, Any] = event.model_dump()
            payload["replayed"] = True
            try:
                await websocket.send_json(payload)
            except Exception:
                return
