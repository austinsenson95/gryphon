import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import App from "@/App"

describe("phone call dashboard", () => {
  it("is available from the shared Mac and phone navigation", async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByTestId("calls-nav"))

    expect(await screen.findByRole("main", { name: "Phone missions" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Calls" })).toBeInTheDocument()
    expect(await screen.findByText("Safe mock line")).toBeInTheDocument()
    expect(screen.getByText("No contacts yet.")).toBeInTheDocument()
  })
})
