"""Browser tools. Only ``browser.open_url`` in Phase 0.

Playwright is imported lazily inside the handler: when it (or its browsers)
is unavailable, the tool degrades to a clearly-marked mock result instead of
failing. The interface stays identical either way.
"""

from __future__ import annotations

from urllib.parse import urlparse

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.tools.schemas import Tool, ToolResult

logger = get_logger("gryphon.tools.browser")

_GOTO_TIMEOUT_MS = 15_000


async def _open_with_playwright(url: str, headless: bool) -> dict:
    from playwright.async_api import async_playwright  # lazy import (optional dep)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=_GOTO_TIMEOUT_MS)
            title = await page.title()
            return {"url": url, "title": title, "opened": True, "mock": False}
        finally:
            await browser.close()


def register(registry, settings: Settings) -> None:
    async def open_url(url: str) -> ToolResult | dict:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult.fail(
                "browser.open_url",
                "INVALID_URL",
                f"Only http/https URLs can be opened, got: {url!r}",
            )
        try:
            return await _open_with_playwright(url, settings.browser_headless)
        except Exception as exc:  # ImportError, missing browsers, navigation errors...
            logger.info(
                "tools.browser.mock_fallback",
                extra={"url": url, "reason": str(exc)[:200]},
            )
            return {
                "url": url,
                "opened": False,
                "mock": True,
                "note": "playwright unavailable",
            }

    registry.register(
        Tool(
            name="browser.open_url",
            description="Open a URL in a headless browser and return the page title.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "http(s) URL to open."}
                },
                "required": ["url"],
            },
            permission="safe",
            handler=open_url,
        )
    )
