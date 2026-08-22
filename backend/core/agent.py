"""Agent runtime (SPEC §2 Agent runtime).

``Agent.run(session_id, user_message)`` drives one full turn:
persist message → emit lifecycle events → LLM (with tool schemas) → execute
tool calls through the registry (max 4 iterations) → final response → persist +
complete the task. All errors become structured results; the request handler
never crashes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.core import executor, planner
from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.core.permissions import requires_approval
from backend.memory import retrieval
from backend.memory.database import Database
from backend.events.bus import EventBus
from backend.events.events import EventType, new_event
from backend.llm.base import LLMMessage, LLMProvider
from backend.services.message_service import MessageService
from backend.services.notification_service import NotificationService
from backend.services.task_service import TaskService
from backend.tools.registry import ToolRegistry

logger = get_logger("gryphon.agent")

MAX_TOOL_ITERATIONS = 4


class AgentResult(BaseModel):
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
        # 1. persist the user message, then lifecycle events.
        user_msg = await self._messages.add(session_id, "user", user_message)
        await self._publish(
            EventType.MESSAGE_RECEIVED,
            session_id,
            None,
            {"message_id": user_msg.id, "role": "user", "content": user_message},
        )
        task = await self._tasks.create(session_id, user_message)
        await self._publish(
            EventType.TASK_STARTED, session_id, task.id, {"input": user_message}
        )
        await self._tasks.mark_running(task.id)
        await self._publish(EventType.AGENT_STARTED, session_id, task.id, {})

        try:
            response_text, tool_records = await self._conversation_loop(
                session_id, task.id
            )
        except Exception as exc:  # structured failure, never crash the handler
            logger.exception("agent.run_failed", extra={"task_id": task.id})
            error = {"code": "AGENT_ERROR", "message": str(exc)}
            await self._tasks.fail(task.id, str(exc))
            await self._publish(EventType.TASK_FAILED, session_id, task.id, {"error": error})
            await self._notifications.create(
                "error", "Task failed", f"{type(exc).__name__}: {exc}"
            )
            assistant_msg = await self._messages.add(
                session_id,
                "assistant",
                "I ran into an internal error while handling that request.",
            )
            return AgentResult(
                message_id=assistant_msg.id,
                task_id=task.id,
                session_id=session_id,
                response="I ran into an internal error while handling that request.",
                tool_calls=[],
                error=error,
            )

        # 4. persist assistant response, close out the task.
        assistant_msg = await self._messages.add(session_id, "assistant", response_text)
        await self._publish(
            EventType.AGENT_RESPONSE,
            session_id,
            task.id,
            {"message_id": assistant_msg.id, "response": response_text},
        )
        await self._tasks.complete(task.id, response_text)
        await self._publish(EventType.TASK_COMPLETED, session_id, task.id, {"result": response_text})
        return AgentResult(
            message_id=assistant_msg.id,
            task_id=task.id,
            session_id=session_id,
            response=response_text,
            tool_calls=tool_records,
        )

    # ------------------------------------------------------------------ loop

    async def _conversation_loop(
        self, session_id: str, task_id: str
    ) -> tuple[str, list[dict]]:
        history = await self._messages.history(session_id, limit=planner.HISTORY_LIMIT)
        messages = planner.build_messages(history)
        tools = planner.select_tools(self._registry)
        tool_records: list[dict] = []

        for _iteration in range(MAX_TOOL_ITERATIONS):
            await self._publish(EventType.AGENT_THINKING, session_id, task_id, {})
            llm_response = await self._provider.generate(messages, tools=tools)

            if not llm_response.tool_calls:
                return llm_response.content or "", tool_records

            for tool_call in llm_response.tool_calls:
                result = await self._handle_tool_call(session_id, task_id, tool_call, tool_records)
                messages.append(
                    LLMMessage(
                        role="tool",
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=result.model_dump_json(),
                    )
                )

        return (
            "I reached the maximum number of tool steps for one turn and stopped here.",
            tool_records,
        )

    async def _handle_tool_call(self, session_id: str, task_id: str, tool_call, tool_records: list[dict]):
        tool = self._registry.get(tool_call.name)

        # Permission gate. CONFIRM tools emit USER_APPROVAL_REQUIRED; in Phase 0
        # the approval is then granted automatically (no human round-trip yet).
        if tool is not None and requires_approval(tool.permission):
            await self._publish(
                EventType.USER_APPROVAL_REQUIRED,
                session_id,
                task_id,
                {
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                    # Phase 0: auto-approved immediately after this event (see README).
                    "auto_approved": True,
                },
            )
            await self._notifications.create(
                "info",
                "Approval required",
                f"Tool {tool_call.name} requested approval (auto-approved in Phase 0).",
            )

        await self._publish(
            EventType.TOOL_CALL_STARTED,
            session_id,
            task_id,
            {"tool_call_id": tool_call.id, "tool": tool_call.name, "arguments": tool_call.arguments},
        )
        result = await executor.execute_tool(self._registry, tool_call.name, tool_call.arguments)
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
                {"tool_call_id": tool_call.id, "tool": tool_call.name, "data": result.data},
            )
        else:
            await self._publish(
                EventType.TOOL_CALL_FAILED,
                session_id,
                task_id,
                {
                    "tool_call_id": tool_call.id,
                    "tool": tool_call.name,
                    "error": result.error.model_dump() if result.error else None,
                },
            )

        record = {
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

    async def _publish(self, type: str, session_id: str | None, task_id: str | None, data: dict) -> None:
        await self._bus.publish(new_event(type, session_id=session_id, task_id=task_id, data=data))
