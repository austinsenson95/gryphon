"""Desktop execution tools (Phase 1).

Real OS-level capabilities executed through safe native mechanisms:
macOS ``open`` via ``asyncio.create_subprocess_exec`` (argument list, never a
shell string), URL scheme validation, an application allowlist, a directory
allowlist, and a configured project registry. The LLM can propose these tools;
this module is where untrusted model output meets the security boundary.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.tools.schemas import Tool, ToolResult

logger = get_logger("griffin.tools.desktop")

_SUBPROCESS_TIMEOUT = 15.0


async def _run_mac_open(args: list[str]) -> tuple[bool, str]:
    """Run macOS ``open`` with an argv list — no shell, no injection surface."""
    open_bin = shutil.which("open")
    if not open_bin:
        return False, "macOS 'open' command not found (unsupported platform)."
    try:
        proc = await asyncio.create_subprocess_exec(
            open_bin,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_SUBPROCESS_TIMEOUT)
    except asyncio.TimeoutError:
        return False, f"'open' timed out after {_SUBPROCESS_TIMEOUT}s."
    if proc.returncode != 0:
        return False, (stderr.decode(errors="replace").strip() or f"exit {proc.returncode}")
    return True, ""


def _apple_quote(text: str) -> str:
    """Quote a string for embedding in an AppleScript literal (no shell)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


async def _run_osascript(script: str) -> tuple[bool, str]:
    """Run AppleScript via osascript with an argv list — no shell, no injection."""
    osascript_bin = shutil.which("osascript")
    if not osascript_bin:
        return False, "osascript not found (unsupported platform)."
    try:
        proc = await asyncio.create_subprocess_exec(
            osascript_bin,
            "-e",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_SUBPROCESS_TIMEOUT)
    except asyncio.TimeoutError:
        return False, f"osascript timed out after {_SUBPROCESS_TIMEOUT}s."
    if proc.returncode != 0:
        return False, (stderr.decode(errors="replace").strip() or f"exit {proc.returncode}")
    return True, ""


def _validate_url(url: str) -> str | None:
    """Return an error message when the URL is not an allowed http(s) URL."""
    if not url or len(url) > 2048 or any(c in url for c in ("\n", "\r", "\x00")):
        return "URL is empty, too long, or contains control characters."
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Only http/https URLs are allowed, got scheme {parsed.scheme!r}."
    if not parsed.netloc:
        return "URL has no host."
    return None


def _resolve_allowed_dir(settings: Settings, raw_path: str) -> tuple[Path | None, str | None]:
    """Expand/normalize a path and confine it to ALLOWED_DIRECTORIES."""
    if not raw_path or any(c in raw_path for c in ("\x00", "\n", "\r")):
        return None, "Invalid path."
    path = Path(raw_path).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:
        return None, f"Cannot resolve path: {exc}"
    allowed = settings.allowed_directory_paths
    if allowed and not any(
        resolved == base or base in resolved.parents for base in allowed
    ):
        return None, (
            f"Path {resolved} is outside the allowed directories "
            f"({settings.allowed_directories})."
        )
    if not resolved.exists():
        return None, f"Path does not exist: {resolved}"
    return resolved, None


def _resolve_application(settings: Settings, name: str) -> str | None:
    """Case-insensitive allowlist lookup; returns the canonical app name."""
    wanted = name.strip().lower()
    for app in settings.allowed_application_list:
        if app.lower() == wanted:
            return app
    return None


def register(registry, settings: Settings) -> None:
    if sys.platform != "darwin":
        logger.warning(
            "tools.desktop.non_macos",
            extra={"platform": sys.platform, "note": "desktop tools will report unsupported"},
        )

    async def open_application(application: str) -> ToolResult:
        canonical = _resolve_application(settings, application)
        if canonical is None:
            return ToolResult.fail(
                "desktop.open_application",
                "UNSUPPORTED_APPLICATION",
                f"Application {application!r} is not in the allowlist "
                f"({settings.allowed_applications}).",
            )
        ok, detail = await _run_mac_open(["-a", canonical])
        if not ok:
            return ToolResult.fail("desktop.open_application", "COMMAND_FAILED", detail)
        return ToolResult.ok(
            "desktop.open_application", {"application": canonical, "opened": True}
        )

    async def open_url(url: str) -> ToolResult:
        error = _validate_url(url)
        if error:
            return ToolResult.fail("desktop.open_url", "INVALID_URL", error)
        args: list[str] = []
        if settings.default_browser:
            canonical = _resolve_application(settings, settings.default_browser)
            if canonical:
                args += ["-a", canonical]
        args.append(url)
        ok, detail = await _run_mac_open(args)
        if not ok:
            return ToolResult.fail("desktop.open_url", "COMMAND_FAILED", detail)
        return ToolResult.ok("desktop.open_url", {"url": url, "opened": True})

    async def search_web(query: str) -> ToolResult:
        query = query.strip()
        if not query or len(query) > 500:
            return ToolResult.fail(
                "desktop.search_web", "INVALID_ARGUMENTS", "Query is empty or too long."
            )
        url = settings.search_engine_url.replace("{query}", quote_plus(query))
        error = _validate_url(url)
        if error:
            return ToolResult.fail("desktop.search_web", "INVALID_URL", error)
        ok, detail = await _run_mac_open([url])
        if not ok:
            return ToolResult.fail("desktop.search_web", "COMMAND_FAILED", detail)
        return ToolResult.ok(
            "desktop.search_web", {"query": query, "url": url, "opened": True}
        )

    async def search_youtube(query: str) -> ToolResult:
        query = query.strip()
        if not query or len(query) > 500:
            return ToolResult.fail(
                "desktop.search_youtube", "INVALID_ARGUMENTS", "Query is empty or too long."
            )
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        ok, detail = await _run_mac_open([url])
        if not ok:
            return ToolResult.fail("desktop.search_youtube", "COMMAND_FAILED", detail)
        return ToolResult.ok(
            "desktop.search_youtube", {"query": query, "url": url, "opened": True}
        )

    async def open_folder(path: str) -> ToolResult:
        resolved, error = _resolve_allowed_dir(settings, path)
        if error or resolved is None:
            return ToolResult.fail("desktop.open_folder", "DISALLOWED_PATH", error or "")
        if not resolved.is_dir():
            return ToolResult.fail(
                "desktop.open_folder", "INVALID_ARGUMENTS", f"Not a directory: {resolved}"
            )
        ok, detail = await _run_mac_open([str(resolved)])
        if not ok:
            return ToolResult.fail("desktop.open_folder", "COMMAND_FAILED", detail)
        return ToolResult.ok("desktop.open_folder", {"path": str(resolved), "opened": True})

    async def open_project(project: str) -> ToolResult:
        projects = settings.project_registry
        path = projects.get(project.strip().lower())
        if path is None:
            return ToolResult.fail(
                "desktop.open_project",
                "UNKNOWN_PROJECT",
                f"Project {project!r} is not in the configured project registry "
                f"({', '.join(sorted(projects)) or 'empty — set PROJECTS'}).",
            )
        if not path.is_dir():
            return ToolResult.fail(
                "desktop.open_project", "INVALID_ARGUMENTS", f"Not a directory: {path}"
            )
        # Prefer opening the project in VS Code when the CLI exists.
        code_bin = shutil.which("code")
        if code_bin:
            try:
                proc = await asyncio.create_subprocess_exec(
                    code_bin, str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=_SUBPROCESS_TIMEOUT)
                if proc.returncode == 0:
                    return ToolResult.ok(
                        "desktop.open_project",
                        {"project": project, "path": str(path), "opened": True, "via": "vscode"},
                    )
            except asyncio.TimeoutError:
                pass  # fall through to Finder
        ok, detail = await _run_mac_open([str(path)])
        if not ok:
            return ToolResult.fail("desktop.open_project", "COMMAND_FAILED", detail)
        return ToolResult.ok(
            "desktop.open_project",
            {"project": project, "path": str(path), "opened": True, "via": "finder"},
        )

    async def open_terminal(path: str | None = None) -> ToolResult:
        args: list[str] = ["-a", "Terminal"]
        if path:
            resolved, error = _resolve_allowed_dir(settings, path)
            if error or resolved is None:
                return ToolResult.fail(
                    "desktop.open_terminal", "DISALLOWED_PATH", error or ""
                )
            args.append(str(resolved))
        ok, detail = await _run_mac_open(args)
        if not ok:
            return ToolResult.fail("desktop.open_terminal", "COMMAND_FAILED", detail)
        return ToolResult.ok(
            "desktop.open_terminal", {"opened": True, "path": path or None}
        )

    async def close_app(application: str) -> ToolResult:
        canonical = _resolve_application(settings, application)
        if canonical is None:
            return ToolResult.fail(
                "desktop.close_app",
                "UNSUPPORTED_APPLICATION",
                f"Application {application!r} is not in the allowlist "
                f"({settings.allowed_applications}).",
            )
        script = f'quit app "{canonical}"'
        ok, detail = await _run_osascript(script)
        if not ok:
            return ToolResult.fail("desktop.close_app", "COMMAND_FAILED", detail)
        return ToolResult.ok(
            "desktop.close_app", {"application": canonical, "closed": True}
        )

    async def notify(title: str, message: str = "") -> ToolResult:
        title = (title or "").strip()
        message = (message or "").strip()
        if not title and not message:
            return ToolResult.fail(
                "desktop.notification",
                "INVALID_ARGUMENTS",
                "A title (and optionally a message) is required.",
            )
        script = f'display notification {_apple_quote(message)} with title {_apple_quote(title)}'
        ok, detail = await _run_osascript(script)
        if not ok:
            return ToolResult.fail("desktop.notification", "COMMAND_FAILED", detail)
        return ToolResult.ok(
            "desktop.notification", {"title": title, "message": message, "sent": True}
        )

    async def clipboard_read() -> ToolResult:
        proc = await asyncio.create_subprocess_exec(
            "pbpaste",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_SUBPROCESS_TIMEOUT
            )
        except asyncio.TimeoutError:
            return ToolResult.fail(
                "desktop.clipboard_read", "COMMAND_FAILED", "pbpaste timed out."
            )
        if proc.returncode != 0:
            return ToolResult.fail(
                "desktop.clipboard_read",
                "COMMAND_FAILED",
                stderr.decode(errors="replace").strip() or f"exit {proc.returncode}",
            )
        return ToolResult.ok(
            "desktop.clipboard_read", {"text": stdout.decode(errors="replace")}
        )

    async def clipboard_write(text: str) -> ToolResult:
        if len(text) > 1_000_000:
            return ToolResult.fail(
                "desktop.clipboard_write", "INVALID_ARGUMENTS", "Text is too large."
            )
        proc = await asyncio.create_subprocess_exec(
            "pbcopy",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(input=text.encode("utf-8")), timeout=_SUBPROCESS_TIMEOUT
            )
        except asyncio.TimeoutError:
            return ToolResult.fail(
                "desktop.clipboard_write", "COMMAND_FAILED", "pbcopy timed out."
            )
        if proc.returncode != 0:
            return ToolResult.fail(
                "desktop.clipboard_write",
                "COMMAND_FAILED",
                stderr.decode(errors="replace").strip() or f"exit {proc.returncode}",
            )
        return ToolResult.ok(
            "desktop.clipboard_write", {"length": len(text), "written": True}
        )

    registry.register(
        Tool(
            name="desktop.open_application",
            description=(
                "Open an installed macOS application by name. Only applications "
                "in the configured allowlist can be opened."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": (
                            "Application name, e.g. 'Safari'. Allowed: "
                            + ", ".join(settings.allowed_application_list)
                        ),
                    }
                },
                "required": ["application"],
            },
            permission="safe",
            handler=open_application,
        )
    )
    registry.register(
        Tool(
            name="desktop.open_url",
            description="Open an http(s) URL in the user's default browser.",
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
    registry.register(
        Tool(
            name="desktop.search_web",
            description="Open a web search for a query in the user's default browser.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"],
            },
            permission="safe",
            handler=search_web,
        )
    )
    registry.register(
        Tool(
            name="desktop.search_youtube",
            description=(
                "Open YouTube's video results page for a search query in the "
                "user's default browser. Use this instead of web.search when "
                "the user specifically asks to search YouTube."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The YouTube video search query."}
                },
                "required": ["query"],
            },
            permission="safe",
            handler=search_youtube,
        )
    )
    registry.register(
        Tool(
            name="desktop.open_folder",
            description=(
                "Open a folder in Finder. The path must be inside the configured "
                "allowed directories."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Folder path ('~' is expanded).",
                    }
                },
                "required": ["path"],
            },
            permission="safe",
            handler=open_folder,
        )
    )
    registry.register(
        Tool(
            name="desktop.open_project",
            description=(
                "Open a named project from the configured project registry. "
                "Only use when the user explicitly names a project alias; "
                "do not use this to open an application."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                        "description": (
                            "Project alias. Known: "
                            + (", ".join(sorted(settings.project_registry)) or "none configured")
                        ),
                    }
                },
                "required": ["project"],
            },
            permission="safe",
            handler=open_project,
        )
    )
    registry.register(
        Tool(
            name="desktop.open_terminal",
            description="Open a terminal window, optionally in an allowed directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional working directory (must be allowed).",
                    }
                },
                "required": [],
            },
            permission="safe",
            handler=open_terminal,
        )
    )
    registry.register(
        Tool(
            name="desktop.open_app",
            description=(
                "Alias of desktop.open_application: open an installed macOS "
                "application by name (allowlisted)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": "Application name, e.g. 'Safari'. Allowed: "
                        + ", ".join(settings.allowed_application_list),
                    }
                },
                "required": ["application"],
            },
            permission="safe",
            handler=open_application,
        )
    )
    registry.register(
        Tool(
            name="desktop.close_app",
            description=(
                "Quit an installed macOS application by name (allowlisted)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": "Application name, e.g. 'Safari'. Allowed: "
                        + ", ".join(settings.allowed_application_list),
                    }
                },
                "required": ["application"],
            },
            permission="safe",
            handler=close_app,
        )
    )
    registry.register(
        Tool(
            name="desktop.notification",
            description="Show a macOS notification with a title and optional message.",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Notification title."},
                    "message": {"type": "string", "description": "Optional message body."},
                },
                "required": ["title"],
            },
            permission="safe",
            handler=notify,
        )
    )
    registry.register(
        Tool(
            name="desktop.clipboard_read",
            description="Read the current text on the macOS clipboard.",
            input_schema={"type": "object", "properties": {}, "required": []},
            permission="safe",
            handler=clipboard_read,
        )
    )
    registry.register(
        Tool(
            name="desktop.clipboard_write",
            description="Write text to the macOS clipboard.",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to put on the clipboard."}
                },
                "required": ["text"],
            },
            permission="confirm",
            handler=clipboard_write,
        )
    )
