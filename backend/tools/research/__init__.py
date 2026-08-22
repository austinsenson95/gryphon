"""Web tools. Only ``web.search`` in Phase 0.

When SEARCH_API_KEY + SEARCH_API_URL are configured, a real HTTP GET is made
(10s timeout). Otherwise a clearly-marked mock result set is returned. Either
way the tool must never crash the app.
"""

from __future__ import annotations

import httpx

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.tools.schemas import Tool, ToolResult

logger = get_logger("gryphon.tools.web")

_SEARCH_TIMEOUT = 10.0


async def _real_search(settings: Settings, query: str) -> dict:
    async with httpx.AsyncClient(timeout=_SEARCH_TIMEOUT) as client:
        response = await client.get(
            settings.search_api_url,
            params={"q": query, "api_key": settings.search_api_key},
        )
        response.raise_for_status()
        payload = response.json()
    results = payload.get("results", payload if isinstance(payload, list) else [])
    return {
        "query": query,
        "results": [
            {
                "title": item.get("title", ""),
                "url": item.get("url", item.get("link", "")),
                "snippet": item.get("snippet", item.get("content", "")),
            }
            for item in results[:5]
        ],
        "mock": False,
    }


def _mock_results(query: str) -> dict:
    return {
        "query": query,
        "results": [
            {
                "title": f"{query} — Overview",
                "url": f"https://example.com/search/{query.replace(' ', '-')}",
                "snippet": f"A general overview of {query} (stub result).",
                "mock": True,
            },
            {
                "title": f"{query} — Documentation",
                "url": f"https://docs.example.com/{query.replace(' ', '-')}",
                "snippet": f"Reference documentation related to {query} (stub result).",
                "mock": True,
            },
            {
                "title": f"{query} — Community discussion",
                "url": f"https://forum.example.com/t/{query.replace(' ', '-')}",
                "snippet": f"What people are saying about {query} (stub result).",
                "mock": True,
            },
        ],
        "mock": True,
    }


def register(registry, settings: Settings) -> None:
    async def web_search(query: str) -> ToolResult | dict:
        if settings.search_api_key and settings.search_api_url:
            try:
                return await _real_search(settings, query)
            except Exception as exc:  # never crash the request
                logger.warning("tools.web_search.failed", extra={"error": str(exc)})
                return ToolResult.fail("web.search", "SEARCH_FAILED", str(exc))
        return _mock_results(query)

    registry.register(
        Tool(
            name="web.search",
            description="Search the web for a query and return the top results.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"],
            },
            permission="safe",
            handler=web_search,
        )
    )
