"""Shared application runtime state, assembled once at startup and stored on
``app.state`` so API routers can reach the db, event bus, tool registry and
LLM provider without globals."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from backend.core.config import Settings
from backend.memory.database import Database
from backend.events.bus import EventBus
from backend.events.websocket_manager import WebSocketManager
from backend.llm.base import LLMProvider
from backend.llm.provider import create_provider
from backend.stt.base import SpeechToTextProvider
from backend.tools.registry import ToolRegistry


@dataclass
class AppState:
    settings: Settings
    db: Database
    registry: ToolRegistry
    provider: LLMProvider
    bus: EventBus
    ws_manager: WebSocketManager
    stt: SpeechToTextProvider

    @property
    def llm_mode(self) -> str:
        return self.settings.llm_mode

    @property
    def active_provider_name(self) -> str:
        """Return the currently configured provider key."""
        return self.settings.llm_provider

    def set_provider(self, provider_name: str) -> None:
        """Switch the active LLM provider at runtime."""
        self.settings.llm_provider = provider_name
        self.provider = create_provider(provider_name, self.settings)


def get_state(request: Request) -> AppState:
    return request.app.state.gryphon
