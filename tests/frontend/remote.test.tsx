import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { DesktopRemoteCard } from "@/remote/DesktopRemoteCard"
import { getRemoteStatus, startRemoteSession } from "@/lib/api"
import type { RemoteStatus } from "@/lib/types"

vi.mock("@/lib/api", () => ({
  getRemoteStatus: vi.fn(),
  startRemoteSession: vi.fn(),
  stopRemoteSession: vi.fn(),
}))

const idleStatus: RemoteStatus = {
  supported: true,
  device_name: "Test Mac",
  lan_address: "192.168.1.20",
  state: "idle",
  expires_at: null,
  permissions: { screen_recording: true, accessibility: true },
  ready: true,
  can_start: true,
}

describe("Desktop phone remote setup", () => {
  beforeEach(() => {
    vi.mocked(getRemoteStatus).mockResolvedValue(idleStatus)
    vi.mocked(startRemoteSession).mockResolvedValue({
      ...idleStatus,
      state: "pairing",
      pairing_code: "482913",
      expires_at: "2026-08-23T14:00:00Z",
    })
  })

  it("generates and visibly displays the code used by the phone", async () => {
    const user = userEvent.setup()
    render(<DesktopRemoteCard />)

    await user.click(await screen.findByRole("button", { name: "Start phone remote" }))

    expect(await screen.findByTestId("desktop-pairing-code")).toHaveTextContent("482913")
    expect(screen.getByText(/http:\/\/192\.168\.1\.20:\d+\/\?mode=phone/)).toBeInTheDocument()
    expect(screen.getByLabelText("Scan to pair this phone")).toBeInTheDocument()
    expect(screen.getByText(/Scan to pair/)).toBeInTheDocument()
    expect(startRemoteSession).toHaveBeenCalledTimes(1)
  })
})
