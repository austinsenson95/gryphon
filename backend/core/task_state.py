"""Compact per-run task state / working memory (§8).

The agent maintains a small, structured record of the current mission.  Instead
of injecting the full transcript into every LLM turn, the agent injects a
``CURRENT TASK STATE`` block summarising goal, current app/URL, completed steps,
next step, recent failures, and relevant UI facts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TaskState(BaseModel):
    goal: str
    current_app: str | None = None
    current_url: str | None = None
    completed: list[str] = Field(default_factory=list)
    next_step: str | None = None
    failure_history: list[dict] = Field(default_factory=list)
    relevant_ui: dict = Field(default_factory=dict)

    def update_from_tool(
        self, tool_name: str, arguments: dict, result: dict | None
    ) -> None:
        """Update state after a tool result is observed."""
        data = result if isinstance(result, dict) else {}

        # Track current URL / app from browser and desktop tools.
        url = data.get("url")
        if url:
            self.current_url = url

        if tool_name.startswith("browser."):
            self.current_app = "browser"
        elif tool_name.startswith("desktop.open_application"):
            app = (data or {}).get("application")
            self.current_app = app
            self.completed.append(f"Opened app: {app}")
        elif tool_name == "desktop.open_url":
            self.completed.append(f"Opened URL in default browser: {url}")

        # Browser navigation / interaction observations.
        if tool_name in ("browser.open", "browser.open_url"):
            title = data.get("title", url)
            self.completed.append(f"Loaded {title}")
            self.next_step = "inspect the page and decide the next action"
        elif tool_name == "browser.inspect":
            count = data.get("element_count", 0)
            self.completed.append(f"Observed page ({count} interactive elements)")
            self.next_step = "select and execute the next action"
        elif tool_name == "browser.click":
            target = _target_label(arguments)
            title = data.get("title")
            self.completed.append(f"Clicked {target}")
            if title:
                self.next_step = f"verify navigation to {title}"
            else:
                self.next_step = "verify the result of the click"
        elif tool_name == "browser.type":
            target = _target_label(arguments)
            text = arguments.get("text", "")
            self.completed.append(f"Typed '{text[:40]}' into {target}")
            self.next_step = "submit or observe the result"
        elif tool_name == "browser.scroll":
            self.completed.append("Scrolled the page")
            self.next_step = "observe the newly visible content"

    def record_failure(self, tool_name: str, code: str, message: str) -> None:
        self.failure_history.append(
            {"tool": tool_name, "code": code, "message": message}
        )
        # Keep only the most recent failures to bound context.
        self.failure_history = self.failure_history[-5:]
        self.next_step = f"recover from {code} and retry or replan"

    def to_prompt_text(self) -> str:
        lines = [
            "CURRENT TASK STATE:",
            f"goal: {self.goal}",
            f"current_app: {self.current_app or 'unknown'}",
            f"current_url: {self.current_url or 'unknown'}",
            f"next_step: {self.next_step or 'decide next action'}",
        ]
        if self.completed:
            lines.append("completed:")
            for item in self.completed[-6:]:
                lines.append(f"  - {item}")
        if self.relevant_ui:
            lines.append("relevant_ui:")
            for key, value in self.relevant_ui.items():
                lines.append(f"  {key}: {value}")
        if self.failure_history:
            lines.append("recent_failures:")
            for fail in self.failure_history:
                lines.append(f"  - {fail['tool']}: {fail['code']} — {fail['message']}")
        return "\n".join(lines)


def _target_label(arguments: dict) -> str:
    target = arguments.get("target") or {}
    # Support both nested target objects and flat semantic arguments.
    role = target.get("role") or arguments.get("role")
    name = target.get("name") or arguments.get("name")
    placeholder = target.get("placeholder") or arguments.get("placeholder")
    element = arguments.get("element")
    if name:
        return f"{role or 'element'} '{name}'"
    if role:
        return f"role={role}"
    if placeholder:
        return f"placeholder={placeholder}"
    if element:
        return f"element={element!r}"
    return "target"
