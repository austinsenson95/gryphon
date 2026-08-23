"""Browser navigation primitives: open / back / forward / refresh / wait.

Each navigation emits ``BROWSER_NAVIGATION`` (intent) followed by
``BROWSER_PAGE_LOADED`` (result) through the manager, so the timeline shows
what the browser is doing in real time.
"""

from __future__ import annotations

from urllib.parse import urlparse

from backend.events.events import EventType
from backend.tools.browser.auth import is_sensitive_url
from backend.tools.browser.extraction import compact_page_state
from backend.tools.browser.session import BrowserError, page_snapshot

_TIMEOUT_MS = 15_000


def validate_url(url: str) -> str | None:
    """Return an error message when url is not an allowed http(s) URL."""
    if not url or len(url) > 2048 or any(c in url for c in ("\n", "\r", "\x00")):
        return "URL is empty, too long, or contains control characters."
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Only http/https URLs can be opened, got scheme {parsed.scheme!r}."
    if not parsed.netloc:
        return "URL has no host."
    return None


async def do_open(manager, url: str, timeout_ms: int | None = None) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    timeout = timeout_ms or _TIMEOUT_MS

    await manager.publish(
        EventType.BROWSER_NAVIGATION, {"url": url, "action": "open"}
    )
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception as exc:
        raise BrowserError("NAVIGATION_FAILED", f"Could not load {url}: {exc}")
    await _wait_loaded(page, timeout)
    snapshot = await page_snapshot(manager)
    state = await compact_page_state(manager)
    await manager.publish(
        EventType.BROWSER_PAGE_LOADED,
        {"url": snapshot["url"], "title": snapshot["title"]},
    )
    return {
        "url": snapshot["url"],
        "title": snapshot["title"],
        "opened": True,
        "mock": False,
        "page_state": state,
    }


async def do_back(manager) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    try:
        await page.go_back(wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
    except Exception as exc:
        raise BrowserError("NAVIGATION_FAILED", f"Could not go back: {exc}")
    await _wait_loaded(page, _TIMEOUT_MS)
    snapshot = await page_snapshot(manager)
    return {**snapshot, "page_state": await compact_page_state(manager)}


async def do_forward(manager) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    try:
        await page.go_forward(wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
    except Exception as exc:
        raise BrowserError("NAVIGATION_FAILED", f"Could not go forward: {exc}")
    await _wait_loaded(page, _TIMEOUT_MS)
    snapshot = await page_snapshot(manager)
    return {**snapshot, "page_state": await compact_page_state(manager)}


async def do_refresh(manager) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    try:
        await page.reload(wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
    except Exception as exc:
        raise BrowserError("NAVIGATION_FAILED", f"Could not reload the page: {exc}")
    await _wait_loaded(page, _TIMEOUT_MS)
    snapshot = await page_snapshot(manager)
    return {**snapshot, "page_state": await compact_page_state(manager)}


async def do_wait(manager, milliseconds: int | None = None, selector: str | None = None) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    if selector:
        try:
            await page.locator(selector).first.wait_for(timeout=_TIMEOUT_MS)
        except Exception as exc:
            raise BrowserError("ELEMENT_NOT_FOUND", f"Timed out waiting for {selector!r}: {exc}")
    else:
        ms = max(0, min(int(milliseconds or 500), 30_000))
        import asyncio

        await asyncio.sleep(ms / 1000)
    return await page_snapshot(manager)


async def _wait_loaded(page, timeout_ms: int) -> None:
    """Wait for network idle but tolerate sites that stream forever."""
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5_000))
    except Exception:
        pass


def is_sensitive(url: str) -> bool:
    return is_sensitive_url(url)
