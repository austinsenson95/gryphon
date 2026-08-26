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
from urllib.parse import quote_plus

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
_YOUTUBE_SEARCH_RE = re.compile(
    r"(?:open|go\s+to)\s+youtube\s+(?:(?:and\s+)?(?:then\s+)?)?"
    r"search(?:\s+youtube)?(?:\s+for)?\s+(.+)",
    re.IGNORECASE | re.DOTALL,
)
_SEARCH_YOUTUBE_RE = re.compile(
    r"search\s+youtube(?:\s+for)?\s+(.+)", re.IGNORECASE | re.DOTALL
)
_MEDIA_PLAY_SERVICE_FIRST_RE = re.compile(
    r"(?:open\s+)?(?P<service>youtube|spotify)\s+(?:and\s+)?"
    r"(?:play|listen\s+to)\s+(?P<query>.+)",
    re.IGNORECASE | re.DOTALL,
)
_MEDIA_PLAY_SERVICE_LAST_RE = re.compile(
    r"(?:play|listen\s+to)\s+(?P<query>.+?)\s+"
    r"(?:on|in)\s+(?P<service>youtube|spotify)\b",
    re.IGNORECASE | re.DOTALL,
)
_OPEN_APP_RE = re.compile(
    r"open\s+(?:my\s+)?(safari|chrome|google chrome|firefox|arc|vs\s*code|"
    r"visual studio code|terminal|iterm|notes|calendar|finder|slack|spotify)\b",
    re.IGNORECASE,
)
_OPEN_ANY_APP_RE = re.compile(
    r"^open\s+(?:my\s+)?(.+?)(?:\s+(?:application|app))?[.!]?\s*$",
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
_CALL_CONTACT_RE = re.compile(
    r"\bcall\s+(?:my\s+)?(?:friend\s+)?(?P<name>[A-Za-z][A-Za-z .'-]{0,60}?)\s+"
    r"(?:and\s+ask|to\s+ask|and\s+find\s+out|to\s+find\s+out|about)\s+(?P<mission>.+)",
    re.IGNORECASE | re.DOTALL,
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
    r"""Deterministic rule-based provider used when no model is configured.

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
            user_text = self._latest_user_text(messages)
            media = self._plan_media_playback(user_text)
            if media:
                followup = self._media_playback_followup(messages, *media)
                if followup is not None:
                    return followup
            return LLMResponse(content=self._synthesize_tool_answer(messages))

        user_text = self._latest_user_text(messages)
        lowered = user_text.lower()

        if "time" in lowered:
            return LLMResponse(tool_calls=[_tool_call("system.get_time", {})])

        media = self._plan_media_playback(user_text)
        if media:
            service, query = media
            return LLMResponse(
                tool_calls=[_tool_call("browser.open", self._media_search_args(service, query))]
            )

        # A site-scoped search is one semantic action. Keep it together rather
        # than splitting it into "open YouTube" plus a generic web search.
        youtube = self._plan_youtube_search(user_text)
        if youtube:
            return LLMResponse(tool_calls=[_tool_call(*youtube)])

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

    @staticmethod
    def _latest_user_text(messages: list[LLMMessage]) -> str:
        return next(
            (
                m.content
                for m in reversed(messages)
                if m.role == "user"
                and not m.content.startswith("CURRENT TASK STATE:")
            ),
            "",
        )

    @staticmethod
    def _plan_media_playback(text: str) -> tuple[str, str] | None:
        match = _MEDIA_PLAY_SERVICE_FIRST_RE.search(text)
        if match is None:
            match = _MEDIA_PLAY_SERVICE_LAST_RE.search(text)
        if match is None:
            return None
        service = match.group("service").lower()
        query = match.group("query").strip().rstrip("?.!")
        return (service, query) if query else None

    @staticmethod
    def _media_search_args(service: str, query: str) -> dict:
        encoded = quote_plus(query)
        if service == "youtube":
            return {"url": f"https://www.youtube.com/results?search_query={encoded}"}
        return {"url": f"https://open.spotify.com/search/{encoded}"}

    def _media_playback_followup(
        self,
        messages: list[LLMMessage],
        service: str,
        query: str,
    ) -> LLMResponse | None:
        """Drive a deterministic observe/click/verify media flow in mock mode.

        The tools are still real. This only chooses the next registered tool,
        which lets offline mode exercise the same multi-turn agent loop as a
        live model.
        """
        last = messages[-1]
        try:
            result = json.loads(last.content)
        except (json.JSONDecodeError, TypeError):
            return None

        if not result.get("success"):
            return None
        data = result.get("data") or {}
        if data.get("mock"):
            return None

        if last.name in ("browser.open", "browser.open_url"):
            return LLMResponse(tool_calls=[_tool_call("browser.inspect", {})])

        if last.name == "browser.inspect":
            current_url = str(data.get("url") or (data.get("page_state") or {}).get("url") or "")
            on_player = (
                service == "youtube" and "/watch" in current_url
            ) or (
                service == "spotify" and any(part in current_url for part in ("/track/", "/album/", "/artist/"))
            )
            if on_player:
                pause_control = self._media_control_candidate(data.get("elements") or [], "pause")
                if pause_control is not None:
                    return LLMResponse(
                        content=f'I started playing "{query}" on {service.title()}.'
                    )
                play_control = self._media_control_candidate(data.get("elements") or [], "play")
                if play_control is None:
                    return LLMResponse(
                        content=(
                            f'I opened "{query}" on {service.title()}, but could not '
                            "verify or start playback from the available controls."
                        )
                    )
                return LLMResponse(
                    tool_calls=[
                        _tool_call(
                            "browser.click",
                            {
                                "role": play_control.get("role") or "button",
                                "name": play_control.get("name") or "Play",
                                "index": play_control.get("index"),
                                "wait_ms": 1000,
                            },
                        )
                    ]
                )

            candidate = self._media_result_candidate(service, query, data.get("elements") or [])
            if candidate is None:
                return LLMResponse(
                    content=(
                        f'I opened {service.title()} results for "{query}", but could not '
                        "identify a playable result on the page."
                    )
                )
            args = {
                "role": candidate.get("role") or "link",
                "name": candidate.get("name") or query,
                "index": candidate.get("index"),
                "wait_ms": 1500,
            }
            return LLMResponse(tool_calls=[_tool_call("browser.click", args)])

        if last.name == "browser.click":
            return LLMResponse(tool_calls=[_tool_call("browser.inspect", {})])

        return None

    @staticmethod
    def _media_result_candidate(service: str, query: str, elements: list[dict]) -> dict | None:
        query_terms = [term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2]
        href_markers = ("/watch",) if service == "youtube" else ("/track/", "/album/", "/artist/")
        candidates: list[tuple[int, dict]] = []
        for element in elements:
            if element.get("disabled"):
                continue
            href = str(element.get("href") or "").lower()
            if not any(marker in href for marker in href_markers):
                continue
            name = str(element.get("name") or "").lower()
            score = sum(1 for term in query_terms if term in name)
            candidates.append((score, element))
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    @staticmethod
    def _media_control_candidate(elements: list[dict], action: str) -> dict | None:
        action = action.lower()
        for element in elements:
            if element.get("disabled"):
                continue
            role = str(element.get("role") or "").lower()
            name = str(element.get("name") or "").strip().lower()
            if role == "button" and re.search(rf"\b{re.escape(action)}\b", name):
                return element
        return None

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

        match = _CALL_CONTACT_RE.search(text)
        if match:
            name = match.group("name").strip()
            mission = match.group("mission").strip().rstrip("?.!")
            return (
                "phone.call_contact",
                {"contact_name": name, "mission": mission},
            )

        youtube = self._plan_youtube_search(text)
        if youtube:
            return youtube

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

        match = _OPEN_ANY_APP_RE.search(text)
        if match:
            application = match.group(1).strip().rstrip(".!")
            if application:
                return ("desktop.open_application", {"application": application})

        if "search" in lowered:
            match = _SEARCH_RE.search(text)
            if match:
                query = match.group(1).strip().rstrip("?.!")
                if query:
                    return ("desktop.search_web", {"query": query})

        return None

    @staticmethod
    def _plan_youtube_search(text: str) -> tuple[str, dict] | None:
        match = _YOUTUBE_SEARCH_RE.search(text) or _SEARCH_YOUTUBE_RE.search(text)
        if not match:
            return None
        query = match.group(1).strip().rstrip("?.!")
        return ("desktop.search_youtube", {"query": query}) if query else None

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
        if name == "phone.call_contact":
            mode = "mock mode" if data.get("mock") else "the Vobiz line"
            return (
                f"I queued the call to {data.get('contact_name', 'the contact')} through {mode}. "
                f"Call ID: {data.get('id', 'unknown')}. I’ll post the transcript and findings in Calls."
            )
        if name == "phone.get_call_status":
            summary = data.get("summary")
            return summary or f"The call to {data.get('contact_name', 'the contact')} is {data.get('status', 'unknown')}."
        if name == "phone.cancel_call":
            return f"The call to {data.get('contact_name', 'the contact')} is {data.get('status', 'cancelled')}."
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
        if name == "desktop.search_youtube":
            return f"I opened YouTube results for \"{data.get('query', '')}\"."
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
