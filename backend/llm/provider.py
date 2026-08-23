"""LLM provider selection.

``get_llm_provider(settings)`` returns:
  * :class:`OllamaProvider` when ``LLM_PROVIDER=ollama`` and ``OLLAMA_MODEL``
    is set (local model runtime — Phase 1 default);
  * an OpenAI-compatible provider when ``LLM_PROVIDER=openai_compatible`` AND
    ``LLM_API_KEY`` is set;
  * otherwise the deterministic, network-free :class:`MockLLMProvider`.
The mock is the sanctioned offline fallback (SPEC §2): it is rule-based, but
the tool calls it emits are REAL — the agent executes them through the tool
registry. Phase 1 extends the mock to compose chained requests ("Open Safari
and go to github.com") into multiple structured tool calls so offline runs can
exercise multi-step execution too.
"""

from __future__ import annotations

import json
import re
import uuid

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolCall

logger = get_logger("griffin.llm")

_OPEN_URL_RE = re.compile(r"open\s+(https?://\S+)", re.IGNORECASE)
_GO_TO_URL_RE = re.compile(r"go\s+to\s+(https?://\S+)", re.IGNORECASE)
_GO_TO_SITE_RE = re.compile(
    r"go\s+to\s+(github|google|youtube|hacker\s+news)\b", re.IGNORECASE
)
_SEARCH_RE = re.compile(
    r"search(?:\s+(?:the\s+web\s+)?for)?\s+(.+)", re.IGNORECASE | re.DOTALL
)
_OPEN_APP_RE = re.compile(
    r"open\s+(?:my\s+)?(safari|chrome|google chrome|firefox|arc|vs\s*code|"
    r"visual studio code|terminal|iterm|notes|calendar|finder|slack|spotify)\b",
    re.IGNORECASE,
)
_KNOWN_SITES = {
    "github": "https://github.com",
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "hacker news": "https://news.ycombinator.com",
}
_OPEN_SITE_RE = re.compile(r"open\s+(github|google|youtube|hacker\s+news)\b", re.IGNORECASE)
_OPEN_PROJECT_RE = re.compile(r"open\s+(?:my\s+)?(\w[\w-]*)\s+project\b", re.IGNORECASE)
_OPEN_FOLDER_RE = re.compile(r"open\s+(?:my\s+)?(\w[\w-]*)\s+folder\b", re.IGNORECASE)
_WORKFLOW_RE = re.compile(
    r"(?:start|run)\s+(?:my\s+)?([\w\s-]+?)(?:\s+workflow)?\s*$", re.IGNORECASE
)
# Chained multi-action connectors (Phase 1 multi-step requests).
_CHAIN_RE = re.compile(r"\s+(?:and\s+then|then|and|,)\s+", re.IGNORECASE)

_APP_ALIASES = {
    "safari": "Safari",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "firefox": "Firefox",
    "arc": "Arc",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "notes": "Notes",
    "calendar": "Calendar",
    "finder": "Finder",
    "slack": "Slack",
    "spotify": "Spotify",
}

_WORKFLOW_ALIASES = {
    "development environment": "start_development",
    "development setup": "start_development",
    "dev environment": "start_development",
    "dev setup": "start_development",
    "development": "start_development",
    "research": "research",
    "morning": "morning",
}

_MOCK_IDENTITY = (
    "I'm Griffin, a local-first personal AI assistant (running in mock mode — "
    "no LLM configured). I can open apps and websites, search the web, open "
    "projects and folders, and run workflows. Try: \"Open GitHub\", \"Open "
    "VS Code\", \"Search the web for local news\", or \"Start my development "
    "environment\"."
)


def _tool_call(name: str, arguments: dict) -> LLMToolCall:
    return LLMToolCall(id=f"call_{uuid.uuid4().hex[:12]}", name=name, arguments=arguments)


class MockLLMProvider(LLMProvider):
    """Deterministic rule-based provider used when no model is configured.

    Rules (first match wins, evaluated against the latest user message):
      * contains "time"                          -> system.get_time {}
      * "open <app>" (known alias)               -> desktop.open_application
      * "open my <name> project"                 -> desktop.open_project
      * "open my <name> folder"                  -> desktop.open_folder
      * "open <github|google|youtube|...>"       -> desktop.open_url
      * /open\s+(https?://\S+)/i                 -> desktop.open_url {"url": ...}
      * "go to <site|url>"                       -> browser.open
      * "search [the web] [for] <q>"             -> desktop.search_web
      * "start/run my <workflow>" (known alias)  -> workflow.run
      * chained "X and Y" / "X then Y" requests  -> one tool call per clause
      * otherwise                                -> conversational reply

    When the latest message is a tool result, it synthesizes a natural-language
    sentence from the tool data so the agent can finish the turn.
    """

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        **kw,
    ) -> LLMResponse:
        if not messages:
            return LLMResponse(content=_MOCK_IDENTITY)

        last = messages[-1]
        if last.role == "tool":
            return LLMResponse(content=self._synthesize_tool_answer(messages))

        user_text = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        lowered = user_text.lower()

        if "time" in lowered:
            return LLMResponse(tool_calls=[_tool_call("system.get_time", {})])

        # Compound multi-action requests (Phase 1): one tool call per clause.
        compound = self._plan_compound(user_text)
        if compound:
            return LLMResponse(tool_calls=[_tool_call(n, a) for n, a in compound])

        plan = self._plan_single(user_text)
        if plan:
            name, args = plan
            return LLMResponse(tool_calls=[_tool_call(name, args)])

        return LLMResponse(content=_MOCK_IDENTITY)

    # ------------------------------------------------------------------ planning

    def _plan_compound(self, text: str) -> list[tuple[str, dict]] | None:
        """Split "X and Y" / "X then Y" into a plan only when BOTH clauses
        independently resolve to an action (never for prose with a stray
        'and'). Returns None when not clearly compound."""
        parts = [p.strip() for p in _CHAIN_RE.split(text)]
        if len(parts) < 2:
            return None
        # Avoid false positives on long prose / search queries with "and".
        if len(text) > 120:
            return None
        plans: list[tuple[str, dict]] = []
        for part in parts:
            if not part:
                return None
            plan = self._plan_single(part)
            if plan is None:
                return None
            plans.append(plan)
        return plans

    def _plan_single(self, text: str) -> tuple[str, dict] | None:
        """Resolve one clause to a single (tool, args) plan, or None."""
        lowered = text.lower().strip()

        match = _WORKFLOW_RE.search(text)
        if match and any(k in lowered for k in ("start", "run", "workflow")):
            workflow = _WORKFLOW_ALIASES.get(match.group(1).strip().lower())
            if workflow:
                return ("workflow.run", {"name": workflow})

        match = _OPEN_APP_RE.search(text)
        if match:
            app = _APP_ALIASES[match.group(1).lower().replace("  ", " ")]
            return ("desktop.open_application", {"application": app})

        match = _OPEN_PROJECT_RE.search(text)
        if match:
            return ("desktop.open_project", {"project": match.group(1).lower()})

        match = _OPEN_FOLDER_RE.search(text)
        if match:
            return ("desktop.open_folder", {"path": f"~/{match.group(1).capitalize()}"})

        match = _OPEN_URL_RE.search(text)
        if match:
            return ("desktop.open_url", {"url": match.group(1)})

        match = _GO_TO_URL_RE.search(text)
        if match:
            return ("browser.open", {"url": match.group(1)})

        match = _GO_TO_SITE_RE.search(text)
        if match:
            url = _KNOWN_SITES[re.sub(r"\s+", " ", match.group(1).lower())]
            return ("browser.open", {"url": url})

        match = _OPEN_SITE_RE.search(text)
        if match:
            url = _KNOWN_SITES[re.sub(r"\s+", " ", match.group(1).lower())]
            return ("desktop.open_url", {"url": url})

        if "search" in lowered:
            match = _SEARCH_RE.search(text)
            if match:
                query = match.group(1).strip().rstrip("?.!")
                if query:
                    return ("desktop.search_web", {"query": query})

        return None

    # ------------------------------------------------------------------ synthesis

    def _synthesize_tool_answer(self, messages: list[LLMMessage]) -> str:
        """Build a final natural-language answer from tool result messages."""
        tool_msgs = [m for m in messages if m.role == "tool"]
        if not tool_msgs:
            return "Done."
        parts: list[str] = []
        for msg in tool_msgs:
            try:
                result = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                parts.append(f"Tool {msg.name or 'unknown'} finished.")
                continue
            parts.append(self._describe_tool_result(msg.name or result.get("tool", "unknown"), result))
        return " ".join(parts)

    @staticmethod
    def _describe_tool_result(name: str, result: dict) -> str:
        if not result.get("success"):
            error = (result.get("error") or {}).get("message", "unknown error")
            return f"I tried to run {name}, but it failed: {error}"
        data = result.get("data") or {}
        if name == "system.get_time":
            return (
                f"The current time is {data.get('human', data.get('iso', 'unknown'))} "
                f"({data.get('timezone', 'local timezone')})."
            )
        if name == "system.get_info":
            return (
                f"This is {data.get('app', 'Griffin')} v{data.get('version', '?')} "
                f"running on {data.get('platform', 'this machine')} "
                f"(Python {data.get('python_version', '?')}, host {data.get('hostname', '?')})."
            )
        if name == "web.search":
            results = data.get("results", [])
            lines = [f"I searched for \"{data.get('query', '')}\". Top results:"]
            for idx, item in enumerate(results[:3], start=1):
                lines.append(f"{idx}. {item.get('title', '?')} — {item.get('url', '')}")
            if data.get("mock"):
                lines.append("(mock results — no search API configured)")
            return "\n".join(lines)
        if name in ("desktop.open_url", "browser.open_url", "browser.open"):
            if data.get("opened"):
                extra = f" — page title: \"{data.get('title')}\"" if data.get("title") else ""
                return f"I opened {data.get('url')}{extra}."
            return (
                f"I couldn't open {data.get('url')}: "
                f"{data.get('note', data.get('reason', 'browser unavailable'))}."
            )
        if name == "desktop.search_web":
            return f"I opened a web search for \"{data.get('query', '')}\"."
        if name in ("desktop.open_application", "desktop.open_app"):
            return f"I opened {data.get('application', 'the application')}."
        if name == "desktop.close_app":
            return f"I closed {data.get('application', 'the application')}."
        if name == "desktop.notification":
            return f"I showed a notification: {data.get('title', '')}."
        if name == "desktop.clipboard_read":
            return f"The clipboard contains: {data.get('text', '')[:200]}"
        if name == "desktop.clipboard_write":
            return f"I wrote {data.get('length', 0)} characters to the clipboard."
        if name == "desktop.open_folder":
            return f"I opened the folder {data.get('path', '')}."
        if name == "desktop.open_project":
            return f"I opened the {data.get('project', '')} project at {data.get('path', '')}."
        if name == "desktop.open_terminal":
            return "I opened a terminal window."
        if name == "workflow.run":
            steps = data.get("steps", [])
            done = sum(1 for s in steps if s.get("success"))
            failed = [s for s in steps if not s.get("success")]
            summary = (
                f"Workflow \"{data.get('workflow', '')}\" finished: "
                f"{done}/{len(steps)} steps succeeded."
            )
            if failed:
                names = ", ".join(s.get("command", "?") for s in failed)
                summary += f" Failed steps: {names}."
            return summary
        return f"Tool {name} returned: {json.dumps(data, default=str)}"


class OpenAICompatibleProvider(LLMProvider):
    """Live provider using the ``openai`` SDK against any compatible endpoint."""

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI  # imported lazily; only needed in live mode

        kwargs: dict = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self._client = AsyncOpenAI(**kwargs)
        self._model = settings.llm_model or "gpt-4o-mini"

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        **kw,
    ) -> LLMResponse:
        request: dict = {
            "model": self._model,
            "messages": [self._to_openai_message(m) for m in messages],
        }
        if tools:
            request["tools"] = tools
        completion = await self._client.chat.completions.create(**request)
        choice = completion.choices[0].message
        tool_calls = [
            LLMToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments or "{}"),
            )
            for tc in (choice.tool_calls or [])
        ]
        return LLMResponse(content=choice.content, tool_calls=tool_calls)

    @staticmethod
    def _to_openai_message(msg: LLMMessage) -> dict:
        if msg.role == "assistant" and msg.tool_calls:
            return {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        # History tool messages are flattened to text so a transcript replayed
        # from the DB stays valid even without the original assistant tool_calls.
        if msg.role == "tool" and msg.tool_call_id:
            return {
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": msg.content,
            }
        if msg.role == "tool":
            return {"role": "user", "content": f"[tool {msg.name}] {msg.content}"}
        return {"role": msg.role, "content": msg.content}


def create_provider(provider: str, settings: Settings) -> LLMProvider:
    """Build a provider by name without touching ``settings.llm_provider``."""
    if provider == "ollama" and settings.ollama_model:
        from backend.llm.ollama import OllamaProvider

        logger.info(
            "llm.provider_selected",
            extra={"provider": "ollama", "mode": "live", "model": settings.ollama_model},
        )
        return OllamaProvider(settings)
    if provider == "xai" and settings.xai_api_key:
        from backend.llm.xai import XAIProvider

        logger.info(
            "llm.provider_selected",
            extra={"provider": "xai", "mode": "live", "model": settings.xai_model},
        )
        return XAIProvider(settings)
    if provider == "openai_compatible" and settings.llm_api_key:
        logger.info("llm.provider_selected", extra={"provider": "openai_compatible", "mode": "live"})
        return OpenAICompatibleProvider(settings)
    logger.info("llm.provider_selected", extra={"provider": "mock", "mode": "mock"})
    return MockLLMProvider()


def get_llm_provider(settings: Settings) -> LLMProvider:
    """Factory: Ollama, xAI, or OpenAI-compatible when configured, else mock."""
    return create_provider(settings.llm_provider, settings)
