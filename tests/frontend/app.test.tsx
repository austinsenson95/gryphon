import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import App from "@/App"

describe("App", () => {
  it("renders the dashboard with all GlassCard surfaces", async () => {
    render(<App />)

    expect(screen.getByText("GRYPHON")).toBeInTheDocument()
    expect(screen.getByText("Current Task")).toBeInTheDocument()
    expect(screen.getByText("Activity Timeline")).toBeInTheDocument()
    expect(screen.getByText("Tool Activity")).toBeInTheDocument()
    expect(screen.getByText("Chat")).toBeInTheDocument()
    expect(screen.getByText("Presence")).toBeInTheDocument()

    // health fetch resolves -> live/mock badge and provider toggle appear
    expect(await screen.findByText("MOCK")).toBeInTheDocument()
    expect(screen.getByTestId("connection-dot")).toBeInTheDocument()
    expect(screen.getByTestId("provider-toggle")).toBeInTheDocument()
  })
})
