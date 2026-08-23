import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { RemoteCockpit } from "@/remote/RemoteCockpit"
import {
  getRemoteStatus,
  launchRemoteApplication,
  sendRemoteInput,
} from "@/lib/api"
import type { RemoteStatus } from "@/lib/types"

vi.mock("@/lib/api", () => ({
  getRemoteStatus: vi.fn(),
  getRemoteFrame: vi.fn().mockResolvedValue(new Blob(["frame"], { type: "image/jpeg" })),
  launchRemoteApplication: vi.fn(),
  pairRemote: vi.fn(),
  sendRemoteInput: vi.fn(),
  stopRemoteSession: vi.fn(),
}))

const pairedStatus: RemoteStatus = {
  supported: true,
  device_name: "Test Mac",
  lan_address: "192.168.1.20",
  state: "paired",
  expires_at: "2026-08-23T14:00:00Z",
  permissions: { screen_recording: true, accessibility: true },
  ready: true,
}

describe("Phone remote controls", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.setItem("griffin.remote.token", "paired-token")
    vi.mocked(getRemoteStatus).mockResolvedValue(pairedStatus)
    vi.mocked(sendRemoteInput).mockResolvedValue({ accepted: true })
    vi.mocked(launchRemoteApplication).mockResolvedValue({
      opened: true,
      app: "hermes",
      application: "Hermes",
    })
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:frame"),
      revokeObjectURL: vi.fn(),
    })
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, right: 320, bottom: 180,
      width: 320, height: 180, toJSON: () => ({}),
    })
  })

  it("moves the pointer, scrolls explicitly, and launches an application", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)
    const surface = await screen.findByLabelText("Mac trackpad surface")

    fireEvent.pointerDown(surface, { clientX: 20, clientY: 20, pointerId: 1 })
    fireEvent.pointerMove(surface, { clientX: 160, clientY: 90, pointerId: 1 })
    fireEvent.pointerUp(surface, { clientX: 160, clientY: 90, pointerId: 1 })

    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      expect.objectContaining({ type: "move", x: 0.5, y: 0.5 }),
    ))

    await user.click(screen.getByRole("button", { name: "Scroll", exact: true }))
    fireEvent.pointerDown(surface, { clientX: 160, clientY: 40, pointerId: 2 })
    fireEvent.pointerUp(surface, { clientX: 160, clientY: 120, pointerId: 2 })
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "scroll", dx: 0, dy: 100 },
    ))

    await user.click(screen.getByRole("button", { name: "Open Hermes" }))
    expect(launchRemoteApplication).toHaveBeenCalledWith("paired-token", "hermes")
  })

  it("opens the adaptive landscape cockpit without hiding its shortcuts", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)

    const surface = await screen.findByLabelText("Mac trackpad surface")
    expect(surface.parentElement).toHaveStyle({ aspectRatio: "16 / 9" })
    expect(screen.getByRole("button", { name: "Open Spotify" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open Notes" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open VS Code" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open Terminal" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Open full screen landscape" }))
    expect(await screen.findByRole("button", { name: "Exit full screen" })).toBeInTheDocument()
    expect(surface.closest("section")).toHaveClass("remote-immersive")
  })

  it("supports double-tap and two-finger scroll gestures", async () => {
    render(<RemoteCockpit />)
    const surface = await screen.findByLabelText("Mac trackpad surface")

    fireEvent.pointerDown(surface, { clientX: 80, clientY: 60, pointerId: 1 })
    fireEvent.pointerUp(surface, { clientX: 80, clientY: 60, pointerId: 1 })
    fireEvent.pointerDown(surface, { clientX: 80, clientY: 60, pointerId: 2 })
    fireEvent.pointerUp(surface, { clientX: 80, clientY: 60, pointerId: 2 })
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      expect.objectContaining({ type: "double_tap", x: 0.25, y: expect.any(Number) }),
    ))
    expect(screen.getByRole("status")).toHaveTextContent("Double-click")

    fireEvent.pointerDown(surface, { clientX: 100, clientY: 80, pointerId: 3 })
    fireEvent.pointerDown(surface, { clientX: 200, clientY: 80, pointerId: 4 })
    fireEvent.pointerMove(surface, { clientX: 100, clientY: 110, pointerId: 3 })
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      expect.objectContaining({ type: "scroll", dy: -30 }),
    ))
  })

  it("clicks directly where the phone user taps the mirrored screen", async () => {
    render(<RemoteCockpit />)
    const surface = await screen.findByLabelText("Mac trackpad surface")

    fireEvent.pointerDown(surface, { clientX: 240, clientY: 90, pointerId: 8 })
    fireEvent.pointerUp(surface, { clientX: 240, clientY: 90, pointerId: 8 })

    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "tap", x: 0.75, y: 0.5 },
    ))
    expect(screen.getByRole("status")).toHaveTextContent("Click")
  })

  it("scrolls continuously during a one-finger swipe in Scroll mode", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)
    const surface = await screen.findByLabelText("Mac trackpad surface")

    await user.click(screen.getByRole("button", { name: "Scroll", exact: true }))
    fireEvent.pointerDown(surface, { clientX: 160, clientY: 130, pointerId: 9 })
    fireEvent.pointerMove(surface, { clientX: 160, clientY: 100, pointerId: 9 })

    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "scroll", dx: 0, dy: -60 },
    ))
  })

  it("scrolls the Mac with the spring-centered dashboard slider", async () => {
    render(<RemoteCockpit />)
    const slider = await screen.findByRole("slider", { name: "Scroll active Mac window" })

    fireEvent.change(slider, { target: { value: "24" } })
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "scroll", dx: 0, dy: 48 },
    ))

    fireEvent.change(slider, { target: { value: "10" } })
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "scroll", dx: 0, dy: -28 },
    ))

    fireEvent.pointerUp(slider)
    expect(slider).toHaveValue("0")
  })

  it("sends phone text and confirms delivery before clearing the field", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)

    const input = await screen.findByPlaceholderText("Type into the selected Mac field…")
    await user.type(input, "Hello from iPhone")
    await user.click(screen.getByRole("button", { name: "Send" }))

    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "text", text: "Hello from iPhone" },
    ))
    expect(await screen.findByRole("status")).toHaveTextContent("Text sent to Mac")
    expect(input).toHaveValue("")
  })

  it("keeps unsent phone text visible when Mac input fails", async () => {
    const user = userEvent.setup()
    vi.mocked(sendRemoteInput).mockRejectedValueOnce(new Error("Accessibility permission is missing"))
    render(<RemoteCockpit />)

    const input = await screen.findByPlaceholderText("Type into the selected Mac field…")
    await user.type(input, "Do not lose this")
    await user.click(screen.getByRole("button", { name: "Send" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Accessibility permission is missing")
    expect(input).toHaveValue("Do not lose this")
  })
})
