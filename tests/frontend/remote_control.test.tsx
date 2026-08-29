import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { RemoteCockpit } from "@/remote/RemoteCockpit"
import {
  getRemoteStatus,
  getRemoteApplications,
  getRemoteVolume,
  launchRemoteApplication,
  sendRemoteCommand,
  sendRemoteInput,
  sendRemoteVoice,
} from "@/lib/api"
import type { RemoteStatus } from "@/lib/types"

vi.mock("@/lib/api", () => ({
  getRemoteStatus: vi.fn(),
  getRemoteApplications: vi.fn(),
  getRemoteFrame: vi.fn().mockResolvedValue(new Blob(["frame"], { type: "image/jpeg" })),
  getRemoteVolume: vi.fn(),
  launchRemoteApplication: vi.fn(),
  pairRemote: vi.fn(),
  sendRemoteCommand: vi.fn(),
  sendRemoteInput: vi.fn(),
  sendRemoteVoice: vi.fn(),
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
    sessionStorage.removeItem("griffin.remote.chat.session")
    vi.mocked(getRemoteStatus).mockResolvedValue(pairedStatus)
    vi.mocked(getRemoteVolume).mockResolvedValue({ volume: 42 })
    vi.mocked(getRemoteApplications).mockResolvedValue({ applications: [
      { id: "hermes", name: "Hermes" },
      { id: "Spotify", name: "Spotify" },
      { id: "Notes", name: "Notes" },
      { id: "Visual Studio Code", name: "VS Code" },
      { id: "Terminal", name: "Terminal" },
    ] })
    vi.mocked(sendRemoteInput).mockResolvedValue({ accepted: true })
    vi.mocked(sendRemoteCommand).mockResolvedValue({
      run_id: "run-phone",
      message_id: "message-phone",
      task_id: "task-phone",
      session_id: "session-phone",
      response: "I opened YouTube results for \"ambient focus music\".",
      tool_calls: [{ tool: "desktop.search_youtube" }],
    })
    vi.mocked(sendRemoteVoice).mockResolvedValue({
      run_id: "run-voice-phone",
      message_id: "message-voice-phone",
      task_id: "task-voice-phone",
      session_id: "session-voice-phone",
      transcript: "Open my calendar",
      response: "I opened Calendar.",
      tool_calls: [{ tool: "desktop.open_application" }],
    })
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

  it("selects and moves the active Mac window from the mirrored touch surface", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)
    const surface = await screen.findByLabelText("Mac trackpad surface")

    await user.click(screen.getByRole("button", { name: "Move active window" }))
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "select_window" },
    ))
    await screen.findByText("Drag to move the selected window")

    fireEvent.pointerDown(surface, { clientX: 80, clientY: 60, pointerId: 12 })
    fireEvent.pointerMove(surface, { clientX: 100, clientY: 70, pointerId: 12 })
    fireEvent.pointerUp(surface, { clientX: 100, clientY: 70, pointerId: 12 })

    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "move_window", dx: 1, dy: 1 },
    ))
    expect(screen.getByText("Drag to move the selected window")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Exit window move mode" }))
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "release_window" },
    ))
    expect(screen.queryByText("Drag to move the selected window")).not.toBeInTheDocument()
  })

  it("drops queued window movement as soon as Move mode is exited", async () => {
    const user = userEvent.setup()
    let finishMove!: (value: { accepted: boolean }) => void
    const heldMove = new Promise<{ accepted: boolean }>((resolve) => { finishMove = resolve })
    vi.mocked(sendRemoteInput).mockImplementation(async (_token, input) => {
      if (input.type === "move_window") return heldMove
      return { accepted: true }
    })
    render(<RemoteCockpit />)
    const surface = await screen.findByLabelText("Mac trackpad surface")

    await user.click(screen.getByRole("button", { name: "Move active window" }))
    await screen.findByText("Drag to move the selected window")
    fireEvent.pointerDown(surface, { clientX: 60, clientY: 50, pointerId: 13 })
    fireEvent.pointerMove(surface, { clientX: 100, clientY: 70, pointerId: 13 })
    fireEvent.pointerMove(surface, { clientX: 140, clientY: 90, pointerId: 13 })

    await waitFor(() => expect(
      vi.mocked(sendRemoteInput).mock.calls.filter(([, input]) => input.type === "move_window"),
    ).toHaveLength(1))
    await user.click(screen.getByRole("button", { name: "Pointer", exact: true }))
    finishMove({ accepted: true })

    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "release_window" },
    ))
    expect(vi.mocked(sendRemoteInput).mock.calls.filter(([, input]) => input.type === "move_window")).toHaveLength(1)
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

  it("expands the Ask Griffin terminal for long responses", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)

    const expand = await screen.findByRole("button", { name: "Expand Griffin response" })
    await user.click(expand)

    expect(screen.getByRole("button", { name: "Collapse Griffin response" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByText("ASK GRIFFIN").closest(".griffin-agent-module")).toHaveClass("is-expanded")

    await user.keyboard("{Escape}")
    expect(screen.getByRole("button", { name: "Expand Griffin response" })).toHaveAttribute("aria-pressed", "false")
  })

  it("changes the focused Mac window's full screen state", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)

    await user.click(await screen.findByRole("button", { name: "Put focused window in full screen" }))
    await user.click(screen.getByRole("button", { name: "Take focused window out of full screen" }))

    expect(sendRemoteInput).toHaveBeenCalledWith("paired-token", { type: "enter_fullscreen" })
    expect(sendRemoteInput).toHaveBeenCalledWith("paired-token", { type: "exit_fullscreen" })
  })

  it("uses direct screen gestures without separate mouse action buttons", async () => {
    render(<RemoteCockpit />)

    expect(await screen.findByLabelText("Mac trackpad surface")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Click", exact: true })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Double-click" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Right-click" })).not.toBeInTheDocument()
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

  it("loads and changes the Mac output volume", async () => {
    render(<RemoteCockpit />)
    const slider = await screen.findByRole("slider", { name: "Mac output volume" })

    expect(getRemoteVolume).toHaveBeenCalledWith("paired-token")
    await waitFor(() => expect(slider).toHaveValue("42"))
    fireEvent.change(slider, { target: { value: "68" } })

    expect(screen.getByText("68%")).toBeInTheDocument()
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "volume", volume: 68 },
    ))
  })

  it("streams typing and deletion to the Mac immediately", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)

    const input = await screen.findByPlaceholderText("Live typing into the Mac…")
    await user.type(input, "Hi")

    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "text", text: "i" },
    ))
    await user.click(screen.getByRole("button", { name: "Delete last character" }))
    await waitFor(() => expect(sendRemoteInput).toHaveBeenCalledWith(
      "paired-token",
      { type: "key", key: "backspace" },
    ))
    expect(input).toHaveValue("H")
  })

  it("sends an authenticated text command to Griffin and shows the result", async () => {
    const user = userEvent.setup()
    render(<RemoteCockpit />)

    const input = await screen.findByRole("textbox", { name: "Message Griffin from phone" })
    await user.type(input, "Open YouTube and search for ambient focus music")
    await user.click(screen.getByRole("button", { name: "Send command to Griffin" }))

    await waitFor(() => expect(sendRemoteCommand).toHaveBeenCalledWith(
      "paired-token",
      "Open YouTube and search for ambient focus music",
      null,
    ))
    expect(await screen.findByRole("status", { name: "Griffin response" })).toHaveTextContent(
      "I opened YouTube results for \"ambient focus music\".",
    )
    expect(input).toHaveValue("")
    expect(sessionStorage.getItem("griffin.remote.chat.session")).toBe("session-phone")
  })

  it("records a phone voice command and sends it through Griffin", async () => {
    const user = userEvent.setup()
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true })
    const stopTrack = vi.fn()
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }], getVideoTracks: () => [] })
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    })
    class FakeMediaRecorder {
      state: RecordingState = "inactive"
      mimeType = "audio/webm"
      ondataavailable: ((event: BlobEvent) => void) | null = null
      onerror: (() => void) | null = null
      onstop: (() => void) | null = null
      constructor(_stream: MediaStream) {}
      start() { this.state = "recording" }
      stop() {
        this.state = "inactive"
        this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) } as BlobEvent)
        this.onstop?.()
      }
    }
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder)
    render(<RemoteCockpit />)

    await user.click(await screen.findByRole("button", { name: "Start phone voice command" }))
    expect(getUserMedia).toHaveBeenCalledWith({
      audio: { echoCancellation: true, noiseSuppression: true },
      video: false,
    })
    expect(await screen.findByText(/Listening on this phone/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Stop phone voice command" }))

    await waitFor(() => expect(sendRemoteVoice).toHaveBeenCalledWith(
      "paired-token",
      expect.objectContaining({ type: "audio/webm" }),
      null,
    ))
    expect(await screen.findByText("Heard: Open my calendar")).toBeInTheDocument()
    expect(screen.getByRole("status", { name: "Griffin response" })).toHaveTextContent("I opened Calendar.")
    expect(sessionStorage.getItem("griffin.remote.chat.session")).toBe("session-voice-phone")
    expect(stopTrack).toHaveBeenCalled()
  })

  it("never opens video capture when LAN HTTP blocks live microphone access", async () => {
    const user = userEvent.setup()
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: false })
    render(<RemoteCockpit />)
    const voiceButton = await screen.findByRole("button", { name: "Start phone voice command" })

    await user.click(voiceButton)
    expect(await screen.findByRole("alert")).toHaveTextContent("requires Griffin to be opened over trusted HTTPS")
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(sendRemoteVoice).not.toHaveBeenCalled()
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true })
  })

  it("keeps live phone text visible when Mac input fails", async () => {
    const user = userEvent.setup()
    vi.mocked(sendRemoteInput).mockRejectedValueOnce(new Error("Accessibility permission is missing"))
    render(<RemoteCockpit />)

    const input = await screen.findByPlaceholderText("Live typing into the Mac…")
    await user.type(input, "D")

    expect(await screen.findByRole("alert")).toHaveTextContent("Accessibility permission is missing")
    expect(input).toHaveValue("D")
  })
})
