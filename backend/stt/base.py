"""Speech-to-text provider contract (Phase 1).

All STT providers implement :class:`SpeechToTextProvider` so the voice API
never cares which local engine is underneath. Local-first: no cloud speech
APIs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class STTUnavailableError(RuntimeError):
    """Raised when no local STT engine is usable."""


class STTError(RuntimeError):
    """Raised when transcription itself fails."""


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str, content_type: str = "") -> str:
        """Transcribe an audio file to text."""

    @abstractmethod
    async def health(self) -> dict:
        """Report provider/engine/model availability."""
