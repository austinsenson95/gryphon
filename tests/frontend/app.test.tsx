import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import userEvent from "@testing-library/user-event"

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
    expect(screen.getByText("Phone remote")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Desktop" })).toHaveAttribute("aria-pressed", "true")

    // health fetch resolves -> live/mock badge and provider toggle appear
    expect(await screen.findByText("MOCK")).toBeInTheDocument()
    expect(screen.getByTestId("connection-dot")).toBeInTheDocument()
    expect(screen.getByTestId("provider-toggle")).toBeInTheDocument()
  })

  it("opens the phone remote pairing cockpit", async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole("button", { name: "Phone" }))

    expect(screen.getByRole("heading", { name: "Put your Mac in your hand." })).toBeInTheDocument()
    expect(screen.getByLabelText("Pairing code")).toHaveAttribute("inputmode", "numeric")
    expect(screen.getByRole("button", { name: "Connect to Mac" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Phone" })).toHaveAttribute("aria-pressed", "true")

    await user.click(screen.getByRole("button", { name: "Desktop" }))
    expect(screen.getByText("Current Task")).toBeInTheDocument()
  })
})
