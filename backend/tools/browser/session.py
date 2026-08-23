"""Element addressing, page snapshots and shared browser helpers.

The browser tools prefer *structured element identifiers* (an index returned
by ``browser.inspect``) over fragile CSS selectors (§4). At inspect time each
interactive element gets an index and a best-effort CSS path is remembered in
the manager; later actions re-resolve by that index, or fall back to a CSS
selector / visible text when the model passes one directly.
"""

from __future__ import annotations

import re

_CSS_PATH_JS = """
(el) => {
  if (!(el instanceof Element)) return null;
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1) {
    let sel = node.nodeName.toLowerCase();
    if (node.id) {
      sel += '#' + CSS.escape(node.id);
      parts.unshift(sel);
      break;
    }
    const parent = node.parentElement;
    if (parent) {
      const same = Array.from(parent.children).filter(
        (c) => c.nodeName === node.nodeName
      );
      if (same.length > 1) {
        sel += ':nth-of-type(' + (same.indexOf(node) + 1) + ')';
      }
    }
    parts.unshift(sel);
    node = parent;
  }
  return parts.join(' > ');
}
"""

_ELEMENT_SELECTOR = (
    "a, button, input, select, textarea, "
    "[role='button'], [role='link'], [role='checkbox'], [role='menuitem'], "
    "[role='tab'], [role='textbox'], [role='combobox'], [role='searchbox']"
)

_MAX_INSPECT_ELEMENTS = 60


def _implicit_role(tag: str, type_attr: str | None) -> str:
    """HTML implicit ARIA role mapping for the most common interactive tags."""
    tag = tag.lower()
    type_attr = (type_attr or "").lower()
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "select":
        return "combobox"
    if tag == "textarea":
        return "textbox"
    if tag == "input":
        if type_attr in ("text", "email", "tel", "url"):
            return "textbox"
        if type_attr == "search":
            return "searchbox"
        if type_attr in ("checkbox", "radio"):
            return type_attr
        if type_attr == "submit":
            return "button"
        if type_attr == "number":
            return "spinbutton"
    return tag


class BrowserError(Exception):
    """A structured, LLM-visible browser failure (code maps to a ToolResult)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def page_snapshot(manager) -> dict:
    """Minimal post-action snapshot (url + title) for the LLM."""
    page = manager.page
    try:
        title = await page.title()
    except Exception:
        title = ""
    return {"url": page.url, "title": title}


async def build_css_path(page, element_handle) -> str | None:
    try:
        return await element_handle.evaluate(_CSS_PATH_JS)
    except Exception:
        return None


def _node_name(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "-") or "element"


async def collect_interactive(page, manager) -> list[dict]:
    """Return a compact, LLM-friendly list of interactive GUI elements.

    Each record contains accessibility metadata (role, name, placeholder) plus a
    stable browser element index.  The list is capped to keep context small.
    """
    elements: list[dict] = []
    handles = await page.query_selector_all(_ELEMENT_SELECTOR)
    manager.clear_elements()
    index = 0
    for handle in handles[:_MAX_INSPECT_ELEMENTS]:
        try:
            info = await handle.evaluate(
                """(el) => {
                    const tag = el.tagName.toLowerCase();
                    const typeAttr = el.getAttribute('type') || null;
                    let role = el.getAttribute('role');
                    if (!role) {
                        if (tag === 'a') role = 'link';
                        else if (tag === 'button') role = 'button';
                        else if (tag === 'select') role = 'combobox';
                        else if (tag === 'textarea') role = 'textbox';
                        else if (tag === 'input') {
                            const t = (typeAttr || '').toLowerCase();
                            if (t === 'search') role = 'searchbox';
                            else if (['text','email','tel','url'].includes(t)) role = 'textbox';
                            else if (t === 'checkbox' || t === 'radio') role = t;
                            else if (t === 'submit') role = 'button';
                            else if (t === 'number') role = 'spinbutton';
                            else role = 'textbox';
                        }
                    }
                    let name = el.getAttribute('aria-label') || '';
                    if (!name && el.getAttribute('aria-labelledby')) {
                        try {
                            const ids = el.getAttribute('aria-labelledby').split(/\\s+/);
                            name = ids.map(id => document.getElementById(id)?.innerText?.trim() || '').filter(Boolean).join(' ');
                        } catch (e) {}
                    }
                    if (!name) {
                        const label = el.labels?.[0];
                        name = label?.innerText?.trim() || '';
                    }
                    if (!name) {
                        name = el.innerText?.trim() || '';
                    }
                    const placeholder = el.getAttribute('placeholder') || null;
                    const value = el.value?.slice(0, 120) || '';
                    if (!name && placeholder) name = placeholder;
                    if (!name && value) name = value;
                    return {
                        tag,
                        role: role || tag,
                        name: name.slice(0, 120),
                        type: typeAttr,
                        href: el.getAttribute('href') || null,
                        placeholder,
                        disabled: el.disabled === true,
                    };
                }"""
            )
        except Exception:
            continue
        css = await build_css_path(page, handle)
        if not css:
            continue
        record = {"index": index, **info}
        if info["tag"] == "input" and info["type"] == "password":
            # Safety (§18): never expose password values or their names.
            record["name"] = "[password field — value hidden]"
            record["placeholder"] = None
        elements.append(record)
        manager.remember_element(index, css)
        index += 1
    return elements


async def resolve_element(manager, element: str):
    """Resolve an index / CSS selector / visible text into a Playwright locator.

    This is the legacy entry point; new code should use ``grounding.resolve_target``
    directly.  Raises BrowserError(ELEMENT_NOT_FOUND) when nothing matches.
    """
    from backend.tools.browser import grounding

    page = manager.page
    result = await grounding.resolve_target(page, manager, element=element)
    return result.locator


_CSS_CHARS = re.compile(r"^[.#]?[a-zA-Z0-9_-]+(\[[^\]]*\])?$")


def _looks_like_css(value: str) -> bool:
    """Heuristic: a bare identifier with optional id/class/attr looks CSS-ish."""
    return bool(_CSS_CHARS.match(value)) and (
        value.startswith(("#", ".")) or "[" in value
    )
