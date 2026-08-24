import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import App from "@/App"
import { GriffinProvider, useGriffinEvents } from "@/lib/useGriffinEvents"
import type { EventType, GriffinEvent } from "@/lib/types"
import { jsonResponse, MockWebSocket } from "./setup"

function event(
  id: string,
  type: EventType,
  data: Record<string, unknown> = {},
  sessionId: string | null = null,
  runId: string | null = null,
): GriffinEvent {
  return {
    id,
    type,
    timestamp: `2026-08-24T15:00:0${id}.000Z`,
    session_id: sessionId,
    task_id: type.startsWith("TASK_") || type === "AGENT_RESPONSE" ? "task-phone" : null,
    run_id: runId,
    data,
  }
}

function mockBackend(events: GriffinEvent[]) {
  vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes("/api/events")) return jsonResponse(events)
    if (url.includes("/api/health")) return jsonResponse({ status: "ok", service: "griffin", llm_mode: "live" })
    if (url.includes("/api/llm/provider")) return jsonResponse({ provider: "xai", mode: "live", available: ["ollama", "xai"] })
    if (url.includes("/api/browser")) return jsonResponse({ active: false, mock: false, url: null, title: null })
    return jsonResponse({ error: { code: "not_found", message: "not found" } }, 404)
  })
}

describe("event replay and phone conversation sync", () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.mocked(fetch).mockReset()
  })

  it("leaves Griffin in the state of the newest chronological event", async () => {
    mockBackend([
      event("1", "STT_FAILED", { error: { code: "STT_EMPTY", message: "Old recording failed" } }),
      event("2", "TASK_COMPLETED", { result: "Latest task succeeded" }),
    ])

    function StateProbe() {
      const { avatarState, notifications } = useGriffinEvents()
      return <><div data-testid="avatar-state">{avatarState}</div><div data-testid="notification-count">{notifications.length}</div></>
    }

    render(<GriffinProvider><StateProbe /></GriffinProvider>)
    await waitFor(() => expect(screen.getByTestId("avatar-state")).toHaveTextContent("SUCCESS"))
    expect(screen.getByTestId("notification-count")).toHaveTextContent("0")
  })

  it("shows a phone voice transcript and Griffin reply in the Mac chat", async () => {
    mockBackend([
      event("1", "SESSION_CREATED", { session_id: "session-phone", title: "Hello Griffin" }, "session-phone"),
      event("2", "MESSAGE_RECEIVED", { message_id: "message-user", role: "user", content: "Hello Griffin" }, "session-phone", "run-phone"),
      event("3", "AGENT_RESPONSE", { message_id: "message-assistant", response: "Hello! How can I help?" }, "session-phone", "run-phone"),
      event("4", "TASK_COMPLETED", { result: "Hello! How can I help?" }, "session-phone", "run-phone"),
    ])

    render(<App />)

    expect(await screen.findByText("Hello Griffin")).toBeInTheDocument()
    expect(await screen.findByText("Hello! How can I help?")).toBeInTheDocument()
  })
})
