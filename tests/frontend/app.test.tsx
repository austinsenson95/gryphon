import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import userEvent from "@testing-library/user-event"

import App from "@/App"

describe("App", () => {
  it("renders the voice-first Griffin canvas", () => {
    render(<App />)

    expect(screen.getByText("What would you like to accomplish?")).toBeInTheDocument()
    expect(screen.getByText("System status")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Plan my day" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Griffin account" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Desktop view" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByTestId("mic-button")).toBeInTheDocument()
  })

  it("opens the phone remote pairing cockpit", async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole("button", { name: "Phone" }))

    expect(screen.getByRole("heading", { name: "Put your Mac in your hand." })).toBeInTheDocument()
    expect(screen.getByLabelText("Pairing code")).toHaveAttribute("inputmode", "numeric")
    expect(screen.getByRole("button", { name: "Connect to Mac" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Phone" })).toHaveAttribute("aria-pressed", "true")

    await user.click(screen.getByRole("button", { name: "Desktop view" }))
    expect(screen.getByText("What would you like to accomplish?")).toBeInTheDocument()
  })
})
