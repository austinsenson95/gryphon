import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import App from "@/App"
import { jsonResponse } from "./setup"

const defaultFetch = vi.mocked(fetch).getMockImplementation()!

afterEach(() => vi.mocked(fetch).mockImplementation(defaultFetch))

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

  it("marks a number as authorized when it is saved", async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input).includes("/api/phone/contacts") && init?.method === "POST") {
        return jsonResponse({
          id: "con_anita",
          name: "Anita",
          phone_number: "+919876543210",
          notes: "",
          call_authorized: true,
          authorization_source: "saved_contact",
          created_at: "2026-08-29T00:00:00Z",
        }, 201)
      }
      return defaultFetch(input)
    })
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByTestId("calls-nav"))
    await user.click(screen.getByRole("button", { name: "Add contact" }))
    await user.type(screen.getByLabelText("Contact name"), "Anita")
    await user.type(screen.getByLabelText("Phone number"), "98765 43210")
    await user.click(screen.getByRole("button", { name: "Save & authorize" }))

    expect(await screen.findByText("Authorized for calls")).toBeInTheDocument()
    expect(screen.getByText(/\+919876543210/)).toBeInTheDocument()
  })
})
