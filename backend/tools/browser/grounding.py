"""Semantic grounding layer for browser actions (§5).

The LLM describes *what* it wants to interact with via a semantic target
``{role, name, type, href, placeholder, index}``.  This module resolves that
description into a concrete Playwright locator deterministically, falling back
through the ordered sources defined by the Griffin architecture:

1. Accessibility tree / AX metadata (role + name)
2. DOM role / ARIA
3. Visible text / labels
4. Stable CSS / XPath
5. Browser element index (from browser.inspect)
6. Vision coordinates — stubbed for future work

The layer also exposes helpers for building the compact, LLM-friendly inspect
output used by ``browser.inspect``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.tools.browser.session import BrowserError

_CSS_CHARS = re.compile(r"^[.#]?[a-zA-Z0-9_-]+(\[[^\]]*\])?$")


@dataclass
class GroundingResult:
    """Outcome of resolving a semantic target."""

    locator: object  # Playwright Locator
    confidence: float  # 0.0-1.0
    reason: str
    selector: str | None = None  # human-readable selector hint


def _looks_like_css(value: str) -> bool:
    """Heuristic: a bare identifier with optional id/class/attr looks CSS-ish."""
    return bool(_CSS_CHARS.match(value)) and (
        value.startswith(("#", ".")) or "[" in value
    )


def _describe(target: dict | None, element: str | None) -> str:
    if target:
        parts = [f"{k}={v!r}" for k, v in target.items() if v is not None]
        return "target{" + ", ".join(parts) + "}"
    return f"element={element!r}"


async def _count(locator) -> int:
    try:
        return await locator.count()
    except Exception:
        return 0


async def resolve_target(
    page,
    manager,
    target: dict | None = None,
    element: str | None = None,
) -> GroundingResult:
    """Resolve a semantic target or legacy element reference to a Locator.

    Raises ``BrowserError(ELEMENT_NOT_FOUND)`` when nothing matches.
    """
    target = target or {}
    element = (element or "").strip()

    if not target and not element:
        raise BrowserError("INVALID_ARGUMENTS", "A target or element is required.")

    # Legacy / fallback path: plain element string.
    if element:
        locator, reason = await _resolve_element_string(page, manager, element)
        if locator is not None:
            return GroundingResult(
                locator=locator,
                confidence=0.7,
                reason=f"legacy element resolved: {reason}",
                selector=element,
            )

    # Semantic target path.
    locator, confidence, reason = await _resolve_semantic_target(page, manager, target)
    if locator is not None:
        return GroundingResult(
            locator=locator,
            confidence=confidence,
            reason=reason,
            selector=_describe(target, None),
        )

    raise BrowserError(
        "ELEMENT_NOT_FOUND",
        f"No element matched {_describe(target, element)}. "
        "Re-run browser.inspect and describe the target more precisely.",
    )


async def _resolve_element_string(page, manager, element: str):
    """Resolve a bare string: index, CSS selector, or visible text."""
    if element.isdigit():
        selector = manager.element_selector(int(element))
        if selector:
            locator = page.locator(selector)
            if await _count(locator) > 0:
                return locator, f"inspect index #{element}"
        return None, "index not found"

    if _looks_like_css(element):
        locator = page.locator(element)
        if await _count(locator) > 0:
            return locator, "css selector"
        return None, "css selector not found"

    # Visible text / accessible name fallbacks.
    for locator, reason in (
        (page.get_by_text(element, exact=False).first, "visible text"),
        (page.get_by_role("button", name=re.compile(re.escape(element), re.I)).first, "button name"),
        (page.get_by_role("link", name=re.compile(re.escape(element), re.I)).first, "link name"),
        (page.get_by_label(re.compile(re.escape(element), re.I)).first, "label"),
    ):
        if await _count(locator) > 0:
            return locator, reason

    return None, "string not matched"


async def _resolve_semantic_target(page, manager, target: dict):
    """Try the ordered semantic resolution strategies."""
    role = _norm(target.get("role"))
    name = _norm(target.get("name"))
    tag = _norm(target.get("tag"))
    type_attr = _norm(target.get("type") or target.get("type_attr"))
    href = target.get("href")
    placeholder = target.get("placeholder")
    index = target.get("index")

    # 5. Browser element index (last-resort but cheap).
    if index is not None:
        try:
            idx = int(index)
        except (TypeError, ValueError):
            idx = None
        if idx is not None:
            selector = manager.element_selector(idx)
            if selector:
                locator = page.locator(selector)
                if await _count(locator) > 0:
                    return locator, 0.95, f"inspect index #{idx}"

    # 1/2. Accessibility / DOM role + name (highest confidence).
    if role and name:
        locator = page.get_by_role(
            role, name=re.compile(re.escape(name), re.I)
        ).first
        if await _count(locator) > 0:
            return locator, 0.95, f"role={role} + name={name}"

    if role:
        locator = page.get_by_role(role).first
        if await _count(locator) > 0:
            return locator, 0.8, f"role={role}"

    # 3. Visible text / labels.
    if name:
        for locator, reason, confidence in (
            (page.get_by_text(name, exact=False).first, "visible text", 0.85),
            (page.get_by_role("button", name=re.compile(re.escape(name), re.I)).first, "button name", 0.82),
            (page.get_by_role("link", name=re.compile(re.escape(name), re.I)).first, "link name", 0.82),
            (page.get_by_label(re.compile(re.escape(name), re.I)).first, "label", 0.8),
        ):
            if await _count(locator) > 0:
                return locator, confidence, reason

    # Placeholder (common for inputs).
    if placeholder:
        locator = page.get_by_placeholder(placeholder).first
        if await _count(locator) > 0:
            return locator, 0.85, f"placeholder={placeholder}"

    # 4. Stable-ish CSS by tag / href.
    if href:
        locator = page.locator(f"a[href*='{href}']").first
        if await _count(locator) > 0:
            return locator, 0.75, f"href contains {href}"

    if tag:
        locator = page.locator(tag).first
        if await _count(locator) > 0:
            return locator, 0.6, f"tag={tag}"

    if type_attr:
        locator = page.locator(f"input[type='{type_attr}']").first
        if await _count(locator) > 0:
            return locator, 0.65, f"input[type={type_attr}]"

    return None, 0.0, "no match"


async def refresh_element_map(page, manager) -> list[dict]:
    """Re-run the interactive-element scan and update the manager's index map.

    Returns the compact element list so callers can report it back to the LLM.
    """
    from backend.tools.browser.session import collect_interactive

    return await collect_interactive(page, manager)


def _norm(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None
