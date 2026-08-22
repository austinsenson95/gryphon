"""Local STT provider (Phase 1).

Backend selection order (first usable wins):

1. ``faster-whisper`` Python package, if installed (model from ``STT_MODEL``).
2. whisper.cpp CLI, when ``WHISPER_CPP_BIN`` + ``WHISPER_CPP_MODEL_PATH`` are
   configured. Audio is converted to 16 kHz WAV with macOS ``afconvert``
   (built-in) when it can decode the input, otherwise passed through.
3. Otherwise the provider reports itself unavailable and the voice endpoint
   returns a structured STT_UNAVAILABLE error — never a silent failure.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.stt.base import SpeechToTextProvider, STTError, STTUnavailableError

logger = get_logger("gryphon.stt.local")

_STT_TIMEOUT = 120.0


class LocalSTTProvider(SpeechToTextProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._backend: str | None = None
        self._backend_error: str | None = None

    # ------------------------------------------------------------- backends

    def _select_backend(self) -> str:
        if self._backend:
            return self._backend
        try:
            import faster_whisper  # noqa: F401

            self._backend = "faster-whisper"
            return self._backend
        except ImportError:
            pass
        if (
            self._settings.whisper_cpp_bin
            and self._settings.whisper_cpp_model_path
            and Path(self._settings.whisper_cpp_bin).exists()
            and Path(self._settings.whisper_cpp_model_path).exists()
        ):
            self._backend = "whisper.cpp"
            return self._backend
        raise STTUnavailableError(
            "No local STT engine available. Install faster-whisper "
            "(pip install faster-whisper) or configure WHISPER_CPP_BIN and "
            "WHISPER_CPP_MODEL_PATH for whisper.cpp. Set STT_PROVIDER=disabled "
            "to turn voice input off."
        )

    async def transcribe(self, audio_path: str, content_type: str = "") -> str:
        try:
            backend = self._select_backend()
        except STTUnavailableError:
            raise
        except Exception as exc:
            raise STTUnavailableError(str(exc)) from exc

        if backend == "faster-whisper":
            return await self._transcribe_faster_whisper(audio_path)
        return await self._transcribe_whisper_cpp(audio_path)

    async def _transcribe_faster_whisper(self, audio_path: str) -> str:
        def _run() -> str:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self._settings.stt_model, device="auto", compute_type="int8"
                )
            segments, _info = self._model.transcribe(audio_path)
            return " ".join(seg.text.strip() for seg in segments).strip()

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_run), timeout=_STT_TIMEOUT
            )
        except asyncio.TimeoutError as exc:
            raise STTError(f"Transcription timed out after {_STT_TIMEOUT}s.") from exc
        except Exception as exc:
            raise STTError(f"Transcription failed: {exc}") from exc

    async def _transcribe_whisper_cpp(self, audio_path: str) -> str:
        wav_path = audio_path
        # whisper.cpp needs 16 kHz WAV; try macOS afconvert when available.
        if sys.platform == "darwin" and shutil.which("afconvert"):
            converted = Path(tempfile.mkstemp(suffix=".wav")[1])
            proc = await asyncio.create_subprocess_exec(
                "afconvert", "-f", "WAVE", "-d", "LEI16@16000",
                audio_path, str(converted),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode == 0:
                wav_path = str(converted)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._settings.whisper_cpp_bin,
                "-m", self._settings.whisper_cpp_model_path,
                "-f", wav_path,
                "--no-timestamps",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_STT_TIMEOUT
            )
        except asyncio.TimeoutError as exc:
            raise STTError(f"whisper.cpp timed out after {_STT_TIMEOUT}s.") from exc
        if proc.returncode != 0:
            raise STTError(
                "whisper.cpp failed: " + stderr.decode(errors="replace")[:300]
            )
        return stdout.decode(errors="replace").strip()

    async def health(self) -> dict:
        status = {
            "provider": "local",
            "model": self._settings.stt_model,
            "backend": None,
            "available": False,
            "error": None,
        }
        if self._settings.stt_provider == "disabled":
            status["error"] = "STT disabled by configuration (STT_PROVIDER=disabled)."
            return status
        try:
            status["backend"] = self._select_backend()
            status["available"] = True
        except STTUnavailableError as exc:
            status["error"] = str(exc)
        return status


class DisabledSTTProvider(SpeechToTextProvider):
    async def transcribe(self, audio_path: str, content_type: str = "") -> str:
        raise STTUnavailableError("STT is disabled (STT_PROVIDER=disabled).")

    async def health(self) -> dict:
        return {
            "provider": "disabled",
            "available": False,
            "error": "STT disabled by configuration.",
        }


def get_stt_provider(settings: Settings) -> SpeechToTextProvider:
    if settings.stt_provider == "disabled":
        return DisabledSTTProvider()
    return LocalSTTProvider(settings)
