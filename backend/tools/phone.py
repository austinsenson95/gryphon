"""LLM-visible tools for asynchronous outbound phone missions."""

from __future__ import annotations

from backend.core import context as run_context
from backend.tools.schemas import Tool


def register(registry, service) -> None:
    async def call_contact(contact_name: str, mission: str, questions: list[str] | None = None):
        return await service.start_call(
            contact_name=contact_name,
            mission=mission,
            questions=questions,
            session_id=run_context.get_session_id(),
            task_id=run_context.get_task_id(),
        )

    async def get_call_status(call_id: str):
        call = await service.get_call(call_id)
        if call is None:
            raise ValueError(f"Phone call {call_id!r} was not found.")
        return call

    async def cancel_call(call_id: str):
        return await service.cancel(call_id)

    registry.register(
        Tool(
            name="phone.call_contact",
            description=(
                "Call an authorized saved contact by name on Griffin's Vobiz number to collect information for a mission. "
                "Never accept or dial a raw phone number; only contacts saved in Griffin's local call allowlist are callable. "
                "The call runs in the background and reports findings to the Calls dashboard."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "contact_name": {"type": "string", "description": "Exact name from Griffin's contact list."},
                    "mission": {"type": "string", "description": "Why Griffin is calling and what it must learn."},
                    "questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional ordered questions. Griffin derives one from the mission when omitted.",
                    },
                },
                "required": ["contact_name", "mission"],
            },
            permission="confirm",
            handler=call_contact,
            category="phone",
        )
    )
    registry.register(
        Tool(
            name="phone.get_call_status",
            description="Get the current status, transcript, and findings for a Griffin phone call job.",
            input_schema={
                "type": "object",
                "properties": {"call_id": {"type": "string"}},
                "required": ["call_id"],
            },
            permission="safe",
            handler=get_call_status,
            category="phone",
        )
    )
    registry.register(
        Tool(
            name="phone.cancel_call",
            description="Cancel a queued, ringing, or active Griffin phone call.",
            input_schema={
                "type": "object",
                "properties": {"call_id": {"type": "string"}},
                "required": ["call_id"],
            },
            permission="confirm",
            handler=cancel_call,
            category="phone",
        )
    )
