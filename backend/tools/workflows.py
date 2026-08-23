"""Registered workflows (Phase 1).

A workflow is an explicit, pre-registered sequence of command steps. The LLM
can only *select* a workflow by name (``workflow.run``) — it can never invent
steps. Each step is itself executed through the normal registry/executor
boundary, so allowlists, URL validation and permission checks all still apply.

Three built-in workflows ship with Phase 1:

  * ``start_development`` — VS Code + first configured project + GitHub
  * ``research``          — open a browser search for the configured topic
  * ``morning``           — open the configured news sites
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.tools.schemas import Tool, ToolResult

logger = get_logger("griffin.tools.workflows")


@dataclass(frozen=True)
class WorkflowStep:
    command: str
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Workflow:
    name: str
    description: str
    steps: tuple[WorkflowStep, ...]


def build_workflows(settings: Settings) -> dict[str, Workflow]:
    """The workflow catalog, derived from configuration."""
    projects = settings.project_registry
    first_project = next(iter(sorted(projects)), None)

    dev_steps: list[WorkflowStep] = [
        WorkflowStep("desktop.open_application", {"application": "Visual Studio Code"}),
    ]
    if first_project:
        dev_steps.append(WorkflowStep("desktop.open_project", {"project": first_project}))
    dev_steps.append(WorkflowStep("desktop.open_url", {"url": "https://github.com"}))

    morning_steps = [
        WorkflowStep("desktop.open_url", {"url": url})
        for url in settings.news_site_list
    ] or [WorkflowStep("desktop.open_url", {"url": "https://news.ycombinator.com"})]

    return {
        "start_development": Workflow(
            name="start_development",
            description=(
                "Open the development environment: VS Code"
                + (f", the {first_project!r} project" if first_project else "")
                + ", and GitHub."
            ),
            steps=tuple(dev_steps),
        ),
        "research": Workflow(
            name="research",
            description=f"Open a browser search for the configured research topic ({settings.research_topic!r}).",
            steps=(
                WorkflowStep("desktop.search_web", {"query": settings.research_topic}),
            ),
        ),
        "morning": Workflow(
            name="morning",
            description="Open the configured morning news sites.",
            steps=tuple(morning_steps),
        ),
    }


def register(registry, settings: Settings, bus=None) -> None:
    workflows = build_workflows(settings)

    async def _publish(type: str, data: dict) -> None:
        if bus is None:
            return
        from backend.core import context as run_context
        from backend.events.events import new_event

        await bus.publish(
            new_event(type, run_id=run_context.get_run_id(), data=data)
        )

    async def run_workflow(name: str) -> ToolResult:
        from backend.core import executor  # local import: avoid cycle at load

        workflow = workflows.get(name.strip().lower())
        if workflow is None:
            return ToolResult.fail(
                "workflow.run",
                "UNKNOWN_WORKFLOW",
                f"Workflow {name!r} is not registered. "
                f"Available: {', '.join(sorted(workflows))}.",
            )
        logger.info(
            "workflow.started",
            extra={"workflow": workflow.name, "steps": len(workflow.steps)},
        )
        await _publish(
            "WORKFLOW_STARTED",
            {"workflow": workflow.name, "steps": len(workflow.steps)},
        )
        results: list[dict] = []
        for index, step in enumerate(workflow.steps):
            # Steps always go through the executor boundary: unknown commands,
            # bad arguments and permission failures fail closed per step.
            result = await executor.execute_tool(registry, step.command, step.arguments)
            results.append(
                {
                    "step": index + 1,
                    "command": step.command,
                    "arguments": step.arguments,
                    "success": result.success,
                    "data": result.data if result.success else None,
                    "error": result.error.model_dump() if result.error else None,
                }
            )
        failed = [r for r in results if not r["success"]]
        await _publish(
            "WORKFLOW_COMPLETED",
            {
                "workflow": workflow.name,
                "completed": len(results) - len(failed),
                "failed": len(failed),
            },
        )
        data = {
            "workflow": workflow.name,
            "steps": results,
            "completed": len(results) - len(failed),
            "failed": len(failed),
        }
        if failed:
            return ToolResult(
                success=False,
                tool="workflow.run",
                data=data,
                error={
                    "code": "WORKFLOW_FAILED",
                    "message": (
                        f"{len(failed)} of {len(results)} steps failed in "
                        f"workflow {workflow.name!r}."
                    ),
                },
            )
        return ToolResult.ok("workflow.run", data)

    registry.register(
        Tool(
            name="workflow.run",
            description=(
                "Run a registered multi-step workflow by name. Prefer this over "
                "individual commands when a known workflow matches the request. "
                "Available workflows: "
                + "; ".join(f"{w.name} — {w.description}" for w in workflows.values())
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Workflow name: "
                        + ", ".join(sorted(workflows)),
                    }
                },
                "required": ["name"],
            },
            permission="safe",
            handler=run_workflow,
        )
    )
