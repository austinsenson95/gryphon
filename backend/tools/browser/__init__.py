"""Griffin browser tools (Phase 1): a real, persistent browser subsystem.

Tools registered here (all LOW risk, executed automatically):

  browser.open / browser.open_url  — navigate to an http(s) URL
  browser.back / forward / refresh — history + reload
  browser.inspect                  — structured page snapshot (element indexes)
  browser.extract                  — article-style content extraction
  browser.click / type / scroll    — interaction (by structured element index)
  browser.screenshot               — save a PNG locally
  browser.wait                     — wait for a selector or a fixed delay

The same persistent Playwright context is reused across every tool call
(§15). When Playwright or its browsers are unavailable the tools degrade to a
clearly-marked mock result instead of failing (§AGENTS.md: browser mock
fallback) — the app never crashes.
"""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.events.events import EventType
from backend.tools.browser import (
    extraction,
    interaction,
    manager as manager_mod,
    navigation,
)
from backend.tools.schemas import Tool, ToolResult

logger = get_logger("griffin.tools.browser")

_MOCK_NOTE = "playwright unavailable (mock fallback)"


def _mock_result(tool: str, **extra) -> dict:
    return {"mock": True, "note": _MOCK_NOTE, **extra}


async def _run_tool(manager, tool_name: str, fn, mock_fields: dict, *args):
    """Execute a browser op, returning a ToolResult (success dict or failure)."""
    if not manager.available():
        return ToolResult.ok(tool_name, _mock_result(tool_name, **mock_fields))
    if not await manager.ensure_ready():
        return ToolResult.ok(
            tool_name,
            _mock_result(tool_name, note=f"{_MOCK_NOTE}: {manager.last_error}"),
        )
    try:
        async with manager.guard():
            data = await fn(*args)
        return ToolResult.ok(tool_name, data)
    except Exception as exc:
        code = getattr(exc, "code", "BROWSER_ERROR")
        return ToolResult.fail(tool_name, code, str(exc))


def register(registry, settings, bus=None) -> None:
    manager = manager_mod.BrowserManager(settings)
    manager.bind_bus(bus)
    registry.browser = manager  # exposed for /api/browser status + shutdown

    async def open_url(url: str):
        error = navigation.validate_url(url)
        if error:
            return ToolResult.fail("browser.open", "INVALID_URL", error)
        return await _run_tool(
            manager,
            "browser.open",
            navigation.do_open,
            {"url": url, "opened": False},
            manager,
            url,
        )

    async def open_url_alias(url: str):
        error = navigation.validate_url(url)
        if error:
            return ToolResult.fail("browser.open_url", "INVALID_URL", error)
        return await _run_tool(
            manager,
            "browser.open_url",
            navigation.do_open,
            {"url": url, "opened": False},
            manager,
            url,
        )

    async def back():
        return await _run_tool(manager, "browser.back", navigation.do_back, {}, manager)

    async def forward():
        return await _run_tool(manager, "browser.forward", navigation.do_forward, {}, manager)

    async def refresh():
        return await _run_tool(manager, "browser.refresh", navigation.do_refresh, {}, manager)

    async def inspect():
        return await _run_tool(manager, "browser.inspect", extraction.do_inspect, {}, manager)

    async def extract():
        return await _run_tool(manager, "browser.extract", extraction.do_extract, {}, manager)

    def _build_target(**fields) -> dict | None:
        target = {k: v for k, v in fields.items() if v is not None}
        return target if target else None

    async def click(
        role: str | None = None,
        name: str | None = None,
        tag: str | None = None,
        type: str | None = None,
        href: str | None = None,
        placeholder: str | None = None,
        index: int | None = None,
        element: str | None = None,
        button: str = "left",
        wait_ms: int = 500,
    ):
        target = _build_target(
            role=role,
            name=name,
            tag=tag,
            type=type,
            href=href,
            placeholder=placeholder,
            index=index,
        )
        return await _run_tool(
            manager,
            "browser.click",
            interaction.do_click,
            {},
            manager,
            target,
            element,
            button,
            wait_ms,
        )

    async def type_(
        role: str | None = None,
        name: str | None = None,
        tag: str | None = None,
        type: str | None = None,
        href: str | None = None,
        placeholder: str | None = None,
        index: int | None = None,
        element: str | None = None,
        text: str = "",
        submit: bool = False,
        clear: bool = True,
    ):
        target = _build_target(
            role=role,
            name=name,
            tag=tag,
            type=type,
            href=href,
            placeholder=placeholder,
            index=index,
        )
        return await _run_tool(
            manager,
            "browser.type",
            interaction.do_type,
            {},
            manager,
            target,
            element,
            text,
            submit,
            clear,
        )

    async def scroll(
        direction: str = "down",
        amount: int = 600,
        role: str | None = None,
        name: str | None = None,
        tag: str | None = None,
        type: str | None = None,
        href: str | None = None,
        placeholder: str | None = None,
        index: int | None = None,
        element: str | None = None,
    ):
        target = _build_target(
            role=role,
            name=name,
            tag=tag,
            type=type,
            href=href,
            placeholder=placeholder,
            index=index,
        )
        return await _run_tool(
            manager,
            "browser.scroll",
            interaction.do_scroll,
            {},
            manager,
            direction,
            amount,
            target,
            element,
        )

    async def screenshot(path: str | None = None, full_page: bool = True):
        return await _run_tool(
            manager,
            "browser.screenshot",
            extraction.do_screenshot,
            {},
            manager,
            path,
            full_page,
        )

    async def wait(milliseconds: int | None = None, selector: str | None = None):
        return await _run_tool(
            manager,
            "browser.wait",
            navigation.do_wait,
            {},
            manager,
            milliseconds,
            selector,
        )

    _register_tool = registry.register

    _SEMANTIC_FIELDS = {
        "role": {
            "type": "string",
            "description": (
                "Accessibility role, e.g. 'button', 'link', 'searchbox', "
                "'textbox'. Optional but helpful."
            ),
        },
        "name": {
            "type": "string",
            "description": (
                "Accessible name / visible text of the element. This is the "
                "primary way to identify a target, e.g. 'Search', "
                "'garethdmm/griffin'."
            ),
        },
        "placeholder": {
            "type": "string",
            "description": "Input placeholder text (for inputs).",
        },
        "index": {
            "type": "integer",
            "description": "Last-resort browser.inspect element index.",
        },
    }

    _register_tool(
        Tool(
            name="browser.open",
            description=(
                "Open a URL inside the Griffin-controlled browser window "
                "(Chromium/Playwright) and wait for it to load. Use this when "
                "the user asks to visit a website and you may need to inspect "
                "or interact with it. NOT for opening the user's default browser."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "http(s) URL to open."}
                },
                "required": ["url"],
            },
            permission="safe",
            handler=open_url,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.open_url",
            description=(
                "Alias of browser.open: open a URL inside the Griffin-controlled "
                "browser window (Chromium/Playwright). This is NOT the user's "
                "default browser."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "http(s) URL to open."}
                },
                "required": ["url"],
            },
            permission="safe",
            handler=open_url_alias,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.back",
            description="Go back one page in the browser history.",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe",
            handler=back,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.forward",
            description="Go forward one page in the browser history.",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe",
            handler=forward,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.refresh",
            description="Reload the current page.",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe",
            handler=refresh,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.inspect",
            description=(
                "Observe the current page: returns the URL, title, a compact "
                "list of interactive elements with accessibility metadata "
                "(role, name, placeholder, index), and a page_state summary. "
                "Use role/name to describe targets for browser.click / "
                "browser.type. Call this after navigation or when the agent "
                "needs to re-observe."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe",
            handler=inspect,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.extract",
            description=(
                "Extract structured content from the current page: title, "
                "description, headings, visible text and links."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe",
            handler=extract,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.click",
            description=(
                "Click an interactive element on the current page. Describe the "
                "target semantically with {role, name, tag, href, index} or pass "
                "a legacy element reference (index string, CSS selector, or visible "
                "text). The runtime resolves the target deterministically."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    **_SEMANTIC_FIELDS,
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "Mouse button (default left).",
                    },
                    "wait_ms": {
                        "type": "integer",
                        "description": "Milliseconds to wait after the click (default 500).",
                    },
                },
                "required": ["name"],
            },
            permission="safe",
            handler=click,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.type",
            description=(
                "Type text into an input on the current page. Describe the "
                "target semantically with {role, name, placeholder, index} or "
                "pass a legacy element reference. Set submit=true to press Enter "
                "afterwards (e.g. to submit a search)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    **_SEMANTIC_FIELDS,
                    "text": {"type": "string", "description": "Text to type."},
                    "submit": {
                        "type": "boolean",
                        "description": "Press Enter after typing (default false).",
                    },
                    "clear": {
                        "type": "boolean",
                        "description": "Clear the field before typing (default true).",
                    },
                },
                "required": ["text"],
            },
            permission="safe",
            handler=type_,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.scroll",
            description=(
                "Scroll the current page up or down, optionally scrolling a "
                "specific element into view."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Scroll direction (default down).",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Pixels to scroll (default 600).",
                    },
                    **_SEMANTIC_FIELDS,
                },
                "required": [],
            },
            permission="safe",
            handler=scroll,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.screenshot",
            description=(
                "Capture a screenshot of the current page to a local PNG file "
                "and return its path."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional output path for the PNG.",
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture the full scrollable page (default true).",
                    },
                },
                "required": [],
            },
            permission="safe",
            handler=screenshot,
            category="browser",
        )
    )
    _register_tool(
        Tool(
            name="browser.wait",
            description=(
                "Wait for a CSS selector to appear on the page, or sleep for a "
                "fixed number of milliseconds."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "milliseconds": {
                        "type": "integer",
                        "description": "Sleep duration in milliseconds.",
                    },
                    "selector": {
                        "type": "string",
                        "description": "Optional CSS selector to wait for.",
                    },
                },
                "required": [],
            },
            permission="safe",
            handler=wait,
            category="browser",
        )
    )
