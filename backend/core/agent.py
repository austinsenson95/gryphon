"""Agent runtime (SPEC §2, Phase 1: computer control).

``Agent.run(session_id, user_message)`` drives one full turn as a *run*:
every request creates a unique ``run_id``; every event and tool call emitted
for that request carries it (§9). The loop is:

  persist message → lifecycle events → LLM (with registry tool schemas) →
  permission gate → execute tool calls through the registry → feed results
  back to the LLM → repeat (bounded by settings.agent_max_steps) → final
  response → persist + complete the task.

The permission gate emits permission.required / permission.granted /
permission.denied events. MEDIUM-risk (confirm) tools are auto-approved in
Phase 1 (no human round-trip yet); HIGH-risk (privileged) tools are refused.
All errors become structured results; the request handler never crashes.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from backend.core import context as run_context
from backend.core import executor, planner
from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.core.permissions import is_executable, requires_approval
from backend.core.task_state import TaskState
from backend.memory import retrieval as repository
from backend.memory.database import Database
from backend.events.bus import EventBus
from backend.events.events import EventType, new_event
from backend.llm.base import LLMMessage, LLMProvider
from backend.llm.ollama import OllamaUnavailableError
from backend.services.message_service import MessageService
from backend.services.notification_service import NotificationService
from backend.services.task_service import TaskService
from backend.tools.registry import ToolRegistry

logger = get_logger("gryphon.agent")

MAX_TOOL_ITERATIONS = 4  # fallback when settings.agent_max_steps is unset


class AgentResult(BaseModel):
    run_id: str
    message_id: str
    task_id: str
    session_id: str
    response: str
    tool_calls: list[dict] = Field(default_factory=list)
    error: dict | None = None


class Agent:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        registry: ToolRegistry,
        provider: LLMProvider,
        settings: Settings,
    ) -> None:
        self._db = db
        self._bus = bus
        self._registry = registry
        self._provider = provider
        self._settings = settings
        self._messages = MessageService(db.session_factory)
        self._tasks = TaskService(db.session_factory)
        self._notifications = NotificationService(db.session_factory)

    async def run(self, session_id: str, user_message: str) -> AgentResult:
        run_id = f"run_{uuid.uuid4().hex}"
        run_context.set_run_id(run_id)
        try:
            return await self._run(session_id, user_message, run_id)
        finally:
            run_context.set_run_id(None)

    async def _run(self, session_id: str, user_message: str, run_id: str) -> AgentResult:
        # 1. persist the user message, then lifecycle events.
        user_msg = await self._messages.add(session_id, "user", user_message)
        await self._publish(
            EventType.MESSAGE_RECEIVED,
            session_id,
            None,
            run_id,
            {"message_id": user_msg.id, "role": "user", "content": user_message},
        )
        task = await self._tasks.create(session_id, user_message)
        await self._publish(
            EventType.TASK_STARTED,
            session_id,
            task.id,
            run_id,
            {"input": user_message},
        )
        await self._tasks.mark_running(task.id)
        await self._publish(EventType.AGENT_STARTED, session_id, task.id, run_id, {})

        state = TaskState(goal=user_message)
        try:
            response_text, tool_records = await self._conversation_loop(
                session_id, task.id, run_id, state
            )
        except Exception as exc:  # structured failure, never crash the handler
            logger.exception("agent.run_failed", extra={"task_id": task.id})
            llm_down = isinstance(exc, OllamaUnavailableError)
            code = "LLM_UNAVAILABLE" if llm_down else "AGENT_ERROR"
            user_message = (
                "I couldn't think through that because my local model isn't "
                "reachable right now. Check that Ollama is running and the "
                "configured model is pulled."
                if llm_down
                else "I ran into an internal error while handling that request."
            )
            error = {"code": code, "message": str(exc)}
            await self._tasks.fail(task.id, str(exc))
            await self._publish(
                EventType.TASK_FAILED, session_id, task.id, run_id, {"error": error}
            )
            await self._notifications.create(
                "error", "Task failed", f"{type(exc).__name__}: {exc}"
            )
            assistant_msg = await self._messages.add(
                session_id,
                "assistant",
                user_message,
            )
            return AgentResult(
                run_id=run_id,
                message_id=assistant_msg.id,
                task_id=task.id,
                session_id=session_id,
                response=user_message,
                tool_calls=[],
                error=error,
            )

        # 4. persist assistant response, close out the task.
        assistant_msg = await self._messages.add(session_id, "assistant", response_text)
        await self._publish(
            EventType.AGENT_RESPONSE,
            session_id,
            task.id,
            run_id,
            {"message_id": assistant_msg.id, "response": response_text},
        )
        await self._tasks.complete(task.id, response_text)
        await self._publish(
            EventType.TASK_COMPLETED,
            session_id,
            task.id,
            run_id,
            {"result": response_text},
        )
        return AgentResult(
            run_id=run_id,
            message_id=assistant_msg.id,
            task_id=task.id,
            session_id=session_id,
            response=response_text,
            tool_calls=tool_records,
        )

    # ------------------------------------------------------------------ loop

    async def _conversation_loop(
        self,
        session_id: str,
        task_id: str,
        run_id: str,
        state: TaskState,
    ) -> tuple[str, list[dict]]:
        history = await self._messages.history(session_id, limit=planner.HISTORY_LIMIT)
        messages = planner.build_messages(history, self._registry)
        tools = planner.select_tools(self._registry)
        tool_records: list[dict] = []
        max_steps = getattr(self._settings, "agent_max_steps", MAX_TOOL_ITERATIONS) or MAX_TOOL_ITERATIONS

        # Seed the model with the initial task state.
        self._inject_state_message(messages, state)

        for _iteration in range(max_steps):
            await self._publish(EventType.AGENT_THINKING, session_id, task_id, run_id, {})
            llm_response = await self._provider.generate(messages, tools=tools)

            if not llm_response.tool_calls:
                return llm_response.content or "", tool_records

            # Preserve the assistant's tool-calling message so providers that need
            # it (e.g. Ollama) can ground the following tool results.
            messages.append(
                LLMMessage(
                    role="assistant",
                    content=llm_response.content or "",
                    tool_calls=llm_response.tool_calls,
                )
            )

            for tool_call in llm_response.tool_calls:
                result = await self._handle_tool_call(
                    session_id, task_id, run_id, tool_call, tool_records
                )

                # Update compact working memory after every observation.
                if result.success:
                    state.update_from_tool(
                        tool_call.name, tool_call.arguments, result.data or {}
                    )
                else:
                    err = result.error.model_dump() if result.error else {}
                    state.record_failure(
                        tool_call.name,
                        err.get("code", "UNKNOWN"),
                        err.get("message", "unknown error"),
                    )

                messages.append(
                    LLMMessage(
                        role="tool",
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=result.model_dump_json(),
                    )
                )

            # Re-inject compact state so the next LLM turn reasons over it.
            self._inject_state_message(messages, state)

        return (
            "I reached the maximum number of tool steps for one turn and stopped here.",
            tool_records,
        )

    def _inject_state_message(self, messages: list[LLMMessage], state: TaskState) -> None:
        """Keep one compact task-state message in the conversation context."""
        content = state.to_prompt_text()
        # Replace an existing state message if present; otherwise append.
        for idx, msg in enumerate(messages):
            if msg.role == "user" and msg.content.startswith("CURRENT TASK STATE:"):
                messages[idx] = LLMMessage(role="user", content=content)
                return
        messages.append(LLMMessage(role="user", content=content))

    async def _handle_tool_call(
        self,
        session_id: str,
        task_id: str,
        run_id: str,
        tool_call,
        tool_records: list[dict],
    ):
        tool = self._registry.get(tool_call.name)
        if tool is None:
            # Unknown tool: permission is moot; the executor returns TOOL_NOT_FOUND.
            return await self._execute_and_record(
                session_id, task_id, run_id, tool_call, tool_records
            )

        # Permission gate (spec §14): every tool passes through here.
        if not is_executable(tool.permission):
            await self._publish(
                EventType.PERMISSION_DENIED,
                session_id,
                task_id,
                run_id,
                {
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                    "permission": tool.permission,
                    "message": f"Tool {tool_call.name} is HIGH risk and is disabled.",
                },
            )
            return await self._execute_and_record(
                session_id, task_id, run_id, tool_call, tool_records
            )

        if requires_approval(tool.permission):
            await self._publish(
                EventType.PERMISSION_REQUIRED,
                session_id,
                task_id,
                run_id,
                {
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                    "permission": tool.permission,
                    "message": (
                        f"Tool {tool_call.name} is MEDIUM risk and needs approval."
                    ),
                },
            )
            await self._publish(
                EventType.USER_APPROVAL_REQUIRED,
                session_id,
                task_id,
                run_id,
                {
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                    # Phase 1: auto-approved immediately after this event.
                    "auto_approved": True,
                },
            )
            await self._notifications.create(
                "info",
                "Approval required",
                f"Tool {tool_call.name} requested approval (auto-approved in Phase 1).",
            )
            await self._publish(
                EventType.PERMISSION_GRANTED,
                session_id,
                task_id,
                run_id,
                {
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                    "auto_approved": True,
                },
            )

        return await self._execute_and_record(
            session_id, task_id, run_id, tool_call, tool_records
        )

    async def _execute_and_record(
        self, session_id, task_id, run_id, tool_call, tool_records
    ):
        await self._publish(
            EventType.TOOL_CALL_STARTED,
            session_id,
            task_id,
            run_id,
            {
                "run_id": run_id,
                "tool_call_id": tool_call.id,
                "tool": tool_call.name,
                "arguments": tool_call.arguments,
            },
        )
        result = await executor.execute_tool(
            self._registry,
            tool_call.name,
            tool_call.arguments,
            timeout=self._settings.tool_timeout,
            max_retries=self._settings.max_tool_retries,
        )
        async with self._db.session_factory() as session:
            await repository.add_tool_call(
                session,
                task_id=task_id,
                tool=tool_call.name,
                input_data=tool_call.arguments,
                output=result.data if result.success else None,
                success=result.success,
            )

        if result.success:
            await self._publish(
                EventType.TOOL_CALL_COMPLETED,
                session_id,
                task_id,
                run_id,
                {
                    "run_id": run_id,
                    "tool_call_id": tool_call.id,
                    "tool": tool_call.name,
                    "data": result.data,
                },
            )
        else:
            await self._publish(
                EventType.TOOL_CALL_FAILED,
                session_id,
                task_id,
                run_id,
                {
                    "run_id": run_id,
                    "tool_call_id": tool_call.id,
                    "tool": tool_call.name,
                    "error": result.error.model_dump() if result.error else None,
                },
            )

        record = {
            "run_id": run_id,
            "tool_call_id": tool_call.id,
            "tool": tool_call.name,
            "arguments": tool_call.arguments,
            "success": result.success,
        }
        if result.success:
            record["data"] = result.data
        else:
            record["error"] = result.error.model_dump() if result.error else None
        tool_records.append(record)
        return result

    async def _publish(
        self,
        type: str,
        session_id: str | None,
        task_id: str | None,
        run_id: str | None,
        data: dict,
    ) -> None:
        await self._bus.publish(
            new_event(
                type,
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                data=data,
            )
        )
