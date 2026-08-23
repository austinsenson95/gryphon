"""Ollama LLM provider (Phase 1).

Talks to a local Ollama server over its native HTTP API (``/api/chat`` with
tool support). The provider never executes anything itself — it only proposes
structured tool calls; validation and execution happen downstream in the
agent's registry/executor boundary.

``health_check()`` verifies reachability, model presence, and a minimal
inference round-trip so startup/problems are observable instead of silent.
"""

from __future__ import annotations

import json
import uuid

import httpx

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolCall

logger = get_logger("griffin.llm.ollama")


class OllamaUnavailableError(RuntimeError):
    """Raised when Ollama cannot be reached or the model is missing."""


class OllamaProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._timeout = settings.ollama_timeout

    @property
    def model(self) -> str:
        return self._model

    async def health_check(self) -> dict:
        """Verify: server reachable, model installed, inference works."""
        result = {
            "provider": "ollama",
            "base_url": self._base_url,
            "model": self._model,
            "reachable": False,
            "model_available": False,
            "inference_ok": False,
            "error": None,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                tags = await client.get(f"{self._base_url}/api/tags")
                tags.raise_for_status()
                result["reachable"] = True
                models = [m.get("name", "") for m in tags.json().get("models", [])]
                result["installed_models"] = models
                result["model_available"] = any(
                    m == self._model or m.startswith(f"{self._model}:")
                    for m in models
                )
                if not result["model_available"]:
                    result["error"] = (
                        f"Model {self._model!r} not installed. "
                        f"Run: ollama pull {self._model}"
                    )
                    return result
                probe = await client.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": "Reply with: ok"}],
                        "stream": False,
                    },
                    timeout=self._timeout,
                )
                probe.raise_for_status()
                result["inference_ok"] = bool(
                    probe.json().get("message", {}).get("content")
                )
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        **kw,
    ) -> LLMResponse:
        payload: dict = {
            "model": self._model,
            "messages": [self._to_ollama_message(m) for m in messages],
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat", json=payload
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning("llm.ollama.request_failed", extra={"error": str(exc)})
            raise OllamaUnavailableError(
                f"Ollama request failed: {exc}. Is Ollama running at "
                f"{self._base_url} with model {self._model!r} pulled?"
            ) from exc

        message = body.get("message", {})
        tool_calls: list[LLMToolCall] = []
        for idx, tc in enumerate(message.get("tool_calls") or []):
            function = tc.get("function", {})
            name = function.get("name")
            if not name:
                continue
            arguments = function.get("arguments") or {}
            if not isinstance(arguments, dict):
                # Model output is untrusted: malformed arguments fail closed.
                logger.warning(
                    "llm.ollama.bad_tool_arguments",
                    extra={"tool": name, "raw": str(arguments)[:200]},
                )
                continue
            tool_calls.append(
                LLMToolCall(
                    id=f"ollama_{uuid.uuid4().hex[:12]}_{idx}",
                    name=name,
                    arguments=arguments,
                )
            )
        return LLMResponse(content=message.get("content") or None, tool_calls=tool_calls)

    @staticmethod
    def _to_ollama_message(msg: LLMMessage) -> dict:
        if msg.role == "tool":
            # Ollama accepts tool-role messages keyed by tool name.
            return {"role": "tool", "name": msg.name or "tool", "content": msg.content}
        if msg.role == "assistant" and msg.tool_calls:
            return {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ],
            }
        return {"role": msg.role, "content": msg.content}
