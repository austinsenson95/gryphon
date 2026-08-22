import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChatPanel } from "@/dashboard/ChatPanel"
import { jsonResponse } from "./setup"

describe("ChatPanel", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset()
  })

  it("submits the message to POST /api/chat on Enter and renders the reply", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        message_id: "m1",
        task_id: "t1",
        session_id: "s1",
        response: "Hello from Gryphon!",
        tool_calls: [],
      }),
    )

    render(<ChatPanel />)
    const input = screen.getByTestId("chat-input")

    fireEvent.change(input, { target: { value: "What time is it?" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(url).toContain("/api/chat")
    expect(init.method).toBe("POST")
    expect(JSON.parse(String(init.body))).toEqual({
      message: "What time is it?",
      session_id: null,
    })

    // optimistic user bubble + assistant reply
    expect(screen.getByText("What time is it?")).toBeInTheDocument()
    expect(await screen.findByText("Hello from Gryphon!")).toBeInTheDocument()
  })

  it("sends via the button and surfaces request errors", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ error: { code: "boom", message: "agent exploded" } }, 500),
    )

    render(<ChatPanel />)
    fireEvent.change(screen.getByTestId("chat-input"), {
      target: { value: "hi" },
    })
    fireEvent.click(screen.getByRole("button", { name: /send message/i }))

    expect(await screen.findByText(/agent exploded/)).toBeInTheDocument()
  })
})
