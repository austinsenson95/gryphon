"""Persistent Griffin browser session manager (Phase 1).

Lifecycle (spec §15): Griffin starts → manager initializes → a single
persistent Chromium context is launched (own user-data dir, so logins survive
within the profile) → every browser tool operates on that same page. A fresh
browser context is never spawned per tool call.

The manager also publishes browser.navigation / browser.page_loaded events
through the event bus (stamped with the enclosing run's ``run_id`` via the
run context).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.core import context as run_context
from backend.core.logging import get_logger

logger = get_logger("griffin.tools.browser")


class BrowserManager:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._playwright = None
        self._context = None
        self._page = None
        self._init_lock = asyncio.Lock()  # guards lazy launch
        self._op_lock = asyncio.Lock()  # serializes page operations
        self._element_map: dict[int, str] = {}  # inspect index -> css selector
        self._bus = None
        self._last_error: str | None = None

    # ------------------------------------------------------------- wiring

    def bind_bus(self, bus) -> None:
        self._bus = bus

    def available(self) -> bool:
        """True when the Playwright package is importable (browsers may still
        be missing — ensure_ready() reports that precisely)."""
        try:
            import playwright  # noqa: F401

            return True
        except Exception:
            return False

    @property
    def last_error(self) -> str | None:
        return self._last_error

    # ------------------------------------------------------------- lifecycle

    async def ensure_ready(self) -> bool:
        """Launch the persistent context exactly once; reuse it afterwards."""
        if self._page is not None:
            return True
        async with self._init_lock:
            if self._page is not None:
                return True
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                profile_dir = Path(self._settings.browser_profile_dir).expanduser()
                profile_dir.mkdir(parents=True, exist_ok=True)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=self._settings.browser_headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                self._page = (
                    self._context.pages[0]
                    if self._context.pages
                    else await self._context.new_page()
                )
                logger.info(
                    "tools.browser.ready",
                    extra={
                        "headless": self._settings.browser_headless,
                        "profile": str(profile_dir),
                    },
                )
                return True
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.info(
                    "tools.browser.unavailable",
                    extra={"error": self._last_error[:300]},
                )
                return False

    async def close(self) -> None:
        for closer in (
            lambda: self._context.close() if self._context else None,
            lambda: self._playwright.stop() if self._playwright else None,
        ):
            try:
                result = closer()
                if result is not None:
                    await result
            except Exception:
                pass
        self._context = None
        self._page = None
        self._playwright = None
        self._element_map.clear()

    # ------------------------------------------------------------- access

    @property
    def page(self):
        return self._page

    def guard(self) -> asyncio.Lock:
        return self._op_lock

    def element_selector(self, index: int) -> str | None:
        return self._element_map.get(index)

    def remember_element(self, index: int, selector: str) -> None:
        self._element_map[index] = selector

    def clear_elements(self) -> None:
        self._element_map.clear()

    async def status(self) -> dict:
        if self._page is None:
            return {
                "active": False,
                "mock": not self.available(),
                "url": None,
                "title": None,
            }
        try:
            return {
                "active": True,
                "mock": False,
                "url": self._page.url,
                "title": await self._page.title(),
            }
        except Exception:
            return {"active": True, "mock": False, "url": self._page.url, "title": None}

    # ------------------------------------------------------------- events

    async def publish(self, type: str, data: dict) -> None:
        if self._bus is None:
            return
        from backend.events.events import new_event

        try:
            await self._bus.publish(
                new_event(type, run_id=run_context.get_run_id(), data=data)
            )
        except Exception as exc:
            logger.warning(
                "tools.browser.publish_failed", extra={"error": str(exc)[:200]}
            )
