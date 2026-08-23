"""Page extraction primitives: inspect / extract / screenshot.

``browser.inspect`` is the agent's primary observation tool — it returns a
structured snapshot (URL, title, visible text, interactive elements with
stable indexes) that drives OBSERVE → DECIDE → ACT loops (§16).

Safety (§18): on credential-entry pages the tools refuse to dump content —
they return a note instead of scraping login state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.tools.browser.auth import is_sensitive_url
from backend.tools.browser.session import (
    BrowserError,
    _ELEMENT_SELECTOR,
    collect_interactive,
    page_snapshot,
)

_TEXT_LIMIT = 4_000


def _utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]


async def _read_visible_text(page) -> str:
    try:
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        return ""
    return (text or "").strip()


async def _read_meta_description(page) -> str | None:
    try:
        meta = await page.query_selector("meta[name='description']")
        if meta:
            return (await meta.get_attribute("content") or "").strip() or None
    except Exception:
        pass
    return None


async def _read_headings(page, limit: int = 12) -> list[str]:
    try:
        handles = await page.query_selector_all("h1, h2, h3")
        out: list[str] = []
        for handle in handles[:limit]:
            text = (await handle.inner_text() or "").strip()
            if text:
                out.append(text)
        return out
    except Exception:
        return []


async def compact_page_state(manager) -> dict:
    """Small observation summary for post-navigation / post-action reporting."""
    page = manager.page
    if page is None:
        return {"url": None, "title": None, "element_count": 0}
    try:
        title = await page.title()
    except Exception:
        title = ""
    try:
        count = await page.locator(_ELEMENT_SELECTOR).count()
    except Exception:
        count = 0
    return {
        "url": page.url,
        "title": title,
        "element_count": min(count, 1000),
    }


async def do_inspect(manager) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    url = page.url
    if is_sensitive_url(url):
        return {
            "url": url,
            "title": await page.title(),
            "note": "This page looks like a credential entry point; page "
            "content is not extracted for safety.",
            "sensitive": True,
            "elements": [],
            "element_count": 0,
            "page_state": await compact_page_state(manager),
        }
    title = await page.title()
    text = await _read_visible_text(page)
    elements = await collect_interactive(page, manager)
    return {
        "url": url,
        "title": title,
        "visible_text": text[:_TEXT_LIMIT],
        "text_truncated": len(text) > _TEXT_LIMIT,
        "elements": elements,
        "element_count": len(elements),
        "page_state": await compact_page_state(manager),
    }


async def do_extract(manager) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    url = page.url
    if is_sensitive_url(url):
        return {
            "url": url,
            "title": await page.title(),
            "note": "This page looks like a credential entry point; page "
            "content is not extracted for safety.",
            "sensitive": True,
        }
    text = await _read_visible_text(page)
    links: list[dict] = []
    try:
        handles = await page.query_selector_all("a[href]")
        for handle in handles[:60]:
            href = await handle.get_attribute("href")
            label = (await handle.inner_text() or "").strip()[:100]
            if href and label:
                links.append({"text": label, "href": href})
    except Exception:
        pass
    return {
        "url": url,
        "title": await page.title(),
        "description": await _read_meta_description(page),
        "headings": await _read_headings(page),
        "text": text[:_TEXT_LIMIT],
        "text_truncated": len(text) > _TEXT_LIMIT,
        "links": links,
        "link_count": len(links),
    }


async def do_screenshot(manager, path: str | None = None, full_page: bool = True) -> dict:
    page = manager.page
    if page is None:
        raise BrowserError("BROWSER_CLOSED", "Browser session is not available.")
    shot_dir = Path(manager._settings.browser_screenshot_dir).expanduser()
    shot_dir.mkdir(parents=True, exist_ok=True)
    target = Path(path).expanduser() if path else shot_dir / f"shot_{_utc_slug()}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        await page.screenshot(path=str(target), full_page=full_page)
    except Exception as exc:
        raise BrowserError("SCREENSHOT_FAILED", f"Could not capture screenshot: {exc}")
    return {
        "path": str(target),
        "url": page.url,
        "title": await page.title(),
        "mock": False,
    }
