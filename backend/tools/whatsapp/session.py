"""Dedicated persistent Playwright context for WhatsApp Web."""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.core.logging import get_logger

logger = get_logger("griffin.whatsapp.session")


class WhatsAppSession:
    def __init__(self, settings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self._playwright = self._context = self._page = None

    @property
    def page(self):
        return self._page

    async def ensure_page(self):
        async with self._lock:
            if self._page is not None and not self._page.is_closed():
                return self._page
            from playwright.async_api import async_playwright

            profile = Path(self.settings.griffin_whatsapp_profile_dir).expanduser().resolve()
            profile.mkdir(parents=True, exist_ok=True)
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=self.settings.griffin_whatsapp_headless,
            )
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            logger.info("whatsapp.browser_start", extra={"profile": str(profile), "headless": self.settings.griffin_whatsapp_headless})
            return self._page

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        self._playwright = self._context = self._page = None
