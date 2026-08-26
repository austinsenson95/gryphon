"""Deterministic DOM controller; no model-facing browser primitives."""

from __future__ import annotations

from backend.tools.whatsapp import selectors
from backend.tools.whatsapp.exceptions import (
    WhatsAppComposerNotFound, WhatsAppNotAuthenticated, WhatsAppSendUncertain,
)


class WhatsAppController:
    URL = "https://web.whatsapp.com/"

    def __init__(self, session, timeout_ms: int = 15_000) -> None:
        self.session = session
        self.timeout_ms = timeout_ms

    async def open(self) -> dict:
        page = await self.session.ensure_page()
        if not page.url.startswith(self.URL):
            await page.goto(self.URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
        return await self.status()

    async def _first_visible(self, candidates):
        page = self.session.page
        for selector in candidates:
            locator = page.locator(selector).first
            try:
                if await locator.is_visible(timeout=500):
                    return locator
            except Exception:
                continue
        return None

    async def status(self) -> dict:
        page = self.session.page
        if page is None:
            return {"status": "not_started", "provider": "whatsapp_web", "ready": False}
        if await self._first_visible(selectors.CHAT_LIST_SELECTORS) and await self._first_visible(selectors.SEARCH_SELECTORS):
            state = "authenticated"
        elif await self._first_visible(selectors.QR_SELECTORS):
            state = "awaiting_authentication"
        else:
            state = "loading"
        return {"status": state, "provider": "whatsapp_web", "ready": state == "authenticated"}

    async def search_contact(self, query: str) -> list[dict]:
        status = await self.open()
        if not status["ready"]:
            raise WhatsAppNotAuthenticated("WhatsApp needs to be linked from your phone.")
        box = await self._first_visible(selectors.SEARCH_SELECTORS)
        await box.fill(query)
        page = self.session.page
        rows = page.locator('#pane-side [role="listitem"], #pane-side [data-testid="cell-frame-container"]')
        try:
            await rows.first.wait_for(state="visible", timeout=self.timeout_ms)
        except Exception:
            return []
        matches = []
        for index in range(min(await rows.count(), 20)):
            row = rows.nth(index)
            names = row.locator('[title], span[dir="auto"]')
            for pos in range(min(await names.count(), 4)):
                name = ((await names.nth(pos).get_attribute("title")) or (await names.nth(pos).inner_text())).strip()
                if name and query.casefold() in name.casefold():
                    matches.append({"display_name": name, "secondary_text": None, "confidence": 1.0 if name.casefold() == query.casefold() else 0.8})
                    break
        unique = {m["display_name"]: m for m in matches}
        return list(unique.values())

    async def send_message(self, recipient: str, message: str) -> None:
        matches = await self.search_contact(recipient)
        exact = [m for m in matches if m["display_name"].casefold() == recipient.casefold()]
        if len(exact) != 1:
            raise WhatsAppNotAuthenticated("The approved WhatsApp chat could not be uniquely verified.")
        page = self.session.page
        await page.get_by_title(exact[0]["display_name"], exact=True).first.click(timeout=self.timeout_ms)
        title = await self._first_visible(selectors.CHAT_TITLE_SELECTORS)
        shown = ((await title.get_attribute("title")) or (await title.inner_text())).strip() if title else ""
        if shown.casefold() != recipient.casefold():
            raise WhatsAppSendUncertain("The open chat identity did not match the approved recipient.")
        composer = await self._first_visible(selectors.COMPOSER_SELECTORS)
        if composer is None:
            raise WhatsAppComposerNotFound("WhatsApp Web loaded, but the message composer was not found.")
        await composer.fill(message)
        if (await composer.inner_text()).strip() != message.strip():
            raise WhatsAppSendUncertain("The WhatsApp draft could not be verified; nothing was sent.")
        send = await self._first_visible(selectors.SEND_SELECTORS)
        if send is not None:
            await send.click(timeout=self.timeout_ms)
        else:
            await composer.press("Enter")
        # Once Send is pressed, failure to observe the outgoing bubble is uncertain.
        try:
            await page.locator(".message-out").filter(has_text=message).last.wait_for(state="visible", timeout=self.timeout_ms)
        except Exception as exc:
            raise WhatsAppSendUncertain("The send may have completed, but Griffin could not verify it. Do not retry automatically.") from exc
