"""Browser interaction primitives: click / type / scroll.

All element actions resolve through the semantic grounding layer
(``grounding.resolve_target``).  After each action the runtime re-observes the
page and returns a compact snapshot so the agent can follow the strict
Observe → Act → Observe → Replan loop.
"""

from __future__ import annotations

import asyncio

from backend.tools.browser import extraction, grounding
from backend.tools.browser.session import BrowserError


async def do_click(
    manager,
    target: dict | None = None,
    element: str | None = None,
    button: str = "left",
    wait_ms: int = 500,
) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")

    resolved = await _resolve_with_recovery(page, manager, target, element)
    try:
        await resolved.locator.first.click(button=button, timeout=10_000)
    except Exception as exc:
        raise BrowserError("CLICK_FAILED", f"Could not click target: {exc}")

    if wait_ms and wait_ms > 0:
        await asyncio.sleep(min(int(wait_ms), 5_000) / 1000)
    return await _post_action_snapshot(manager, resolved)


async def do_type(
    manager,
    target: dict | None = None,
    element: str | None = None,
    text: str = "",
    submit: bool = False,
    clear: bool = True,
) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    if not text:
        raise BrowserError("INVALID_ARGUMENTS", "text is required for browser.type")

    resolved = await _resolve_with_recovery(page, manager, target, element)
    try:
        if clear:
            await resolved.locator.first.fill("")
        await resolved.locator.first.type(text, delay=15)
        if submit:
            await resolved.locator.first.press("Enter")
    except Exception as exc:
        raise BrowserError("TYPE_FAILED", f"Could not type into target: {exc}")

    await asyncio.sleep(0.6)
    return await _post_action_snapshot(manager, resolved)


async def do_scroll(
    manager,
    direction: str = "down",
    amount: int = 600,
    target: dict | None = None,
    element: str | None = None,
) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")

    direction = (direction or "down").lower()
    if direction not in ("up", "down"):
        raise BrowserError(
            "INVALID_ARGUMENTS", f"direction must be 'up' or 'down', got {direction!r}."
        )
    delta = abs(int(amount or 600))
    if direction == "up":
        delta = -delta

    if target or element:
        resolved = await _resolve_with_recovery(page, manager, target, element)
        try:
            await resolved.locator.first.evaluate(f"el => el.scrollBy(0, {delta})")
        except Exception as exc:
            raise BrowserError("SCROLL_FAILED", f"Could not scroll target: {exc}")
    else:
        try:
            await page.evaluate(f"window.scrollBy(0, {delta}); true")
        except Exception as exc:
            raise BrowserError("SCROLL_FAILED", f"Could not scroll: {exc}")

    await asyncio.sleep(0.3)
    return await _post_action_snapshot(manager, None)


async def _resolve_with_recovery(page, manager, target, element):
    """Resolve a target, with one automatic re-inspect on ELEMENT_NOT_FOUND."""
    try:
        return await grounding.resolve_target(page, manager, target=target, element=element)
    except BrowserError as first:
        if first.code != "ELEMENT_NOT_FOUND":
            raise
        # One automatic re-observe to refresh the element map.
        await grounding.refresh_element_map(page, manager)
        try:
            return await grounding.resolve_target(page, manager, target=target, element=element)
        except BrowserError:
            raise first


async def _post_action_snapshot(manager, resolved) -> dict:
    """Return a compact post-action observation: page state + grounding metadata."""
    snapshot = await extraction.compact_page_state(manager)
    out = {
        "url": snapshot["url"],
        "title": snapshot["title"],
        "element_count": snapshot["element_count"],
    }
    if resolved is not None:
        out["grounding"] = {
            "confidence": resolved.confidence,
            "reason": resolved.reason,
            "selector": resolved.selector,
        }
    return out
