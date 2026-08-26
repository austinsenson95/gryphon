from backend.core.permissions import SAFE
from backend.tools.schemas import Tool, ToolResult
from backend.tools.whatsapp.exceptions import WhatsAppError


def register(registry, service) -> None:
    async def run(name, call, **kwargs):
        try:
            return ToolResult.ok(name, await call(**kwargs))
        except WhatsAppError as exc:
            return ToolResult.fail(name, exc.code, str(exc))
        except ValueError as exc:
            return ToolResult.fail(name, "WHATSAPP_INVALID_INPUT", str(exc))

    tools = [
        Tool("whatsapp.open", "Open the isolated WhatsApp Web connector and report linking status. This never sends a message.", {"type": "object", "properties": {}, "additionalProperties": False}, SAFE, lambda: run("whatsapp.open", service.open), "whatsapp"),
        Tool("whatsapp.search_contact", "Search WhatsApp chats by name. Never guess when several chats match.", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}, SAFE, lambda query: run("whatsapp.search_contact", service.search_contact, query=query), "whatsapp"),
        Tool("whatsapp.prepare_message", "Prepare a plain-text WhatsApp message for explicit user approval. This does not send. Preserve exact wording and call this before any send.", {"type": "object", "properties": {"recipient": {"type": "string"}, "message": {"type": "string"}}, "required": ["recipient", "message"], "additionalProperties": False}, SAFE, lambda recipient, message: run("whatsapp.prepare_message", service.prepare_message, recipient=recipient, message=message), "whatsapp"),
        Tool("whatsapp.send_message", "Send only a previously prepared and explicitly approved WhatsApp action. Requires the server-issued action ID and opaque token; never fabricate either.", {"type": "object", "properties": {"action_id": {"type": "string"}, "approval_token": {"type": "string"}}, "required": ["action_id", "approval_token"], "additionalProperties": False}, SAFE, lambda action_id, approval_token: run("whatsapp.send_message", service.send, action_id=action_id, approval_token=approval_token), "whatsapp"),
    ]
    for tool in tools:
        registry.register(tool)
