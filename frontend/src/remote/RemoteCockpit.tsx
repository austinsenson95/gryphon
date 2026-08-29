import { useCallback, useEffect, useRef, useState } from "react"
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ChevronDown,
  ChevronUp,
  Command,
  Keyboard,
  Laptop,
  Link2,
  LockKeyhole,
  Maximize2,
  Mic,
  MicOff,
  Minimize2,
  Move,
  MousePointer2,
  MonitorUp,
  Power,
  RefreshCw,
  RotateCcw,
  ScrollText,
  SendHorizontal,
  Settings2,
  ShieldCheck,
  SquareTerminal,
  VolumeX,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  ControlGroup,
  EngravedLabel,
  InstrumentDisplay,
  MetalPanel,
  PhysicalButton,
  RecessedPanel,
  StatusLED,
  WoodPanel,
} from "@/components/griffin/hardware"
import {
  getRemoteFrame,
  getRemoteApplications,
  getRemoteStatus,
  getRemoteVolume,
  launchRemoteApplication,
  openRemoteAccessibilitySettings,
  pairRemote,
  sendRemoteCommand,
  sendRemoteInput,
  sendRemoteVoice,
  stopRemoteSession,
} from "@/lib/api"
import type { RemoteApplication, RemoteApplicationOption, RemoteInput, RemoteStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

const TOKEN_KEY = "griffin.remote.token"
const CHAT_SESSION_KEY = "griffin.remote.chat.session"
const MAX_VOICE_RECORDING_MS = 30_000
type PhoneVoiceState = "idle" | "listening" | "transcribing"

function PermissionPill({ ok, children }: { ok: boolean; children: string }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold",
      ok ? "border-emerald-300/25 bg-emerald-400/10 text-emerald-200" : "border-amber-300/25 bg-amber-400/10 text-amber-100",
    )}>
      {ok ? <ShieldCheck className="h-3.5 w-3.5" /> : <LockKeyhole className="h-3.5 w-3.5" />}
      {children}
    </span>
  )
}

function PairingView({ status, onStatus }: { status: RemoteStatus | null; onStatus: (status: RemoteStatus, token?: string) => void }) {
  const [code, setCode] = useState(new URLSearchParams(location.search).get("pair") ?? "")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const pairedCodeRef = useRef<string | null>(null)

  const pair = async () => {
    setBusy(true)
    setError("")
    try {
      const result = await pairRemote(code)
      onStatus(result, result.token)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not pair with the Mac.")
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (code.length !== 6 || pairedCodeRef.current === code) return
    pairedCodeRef.current = code
    void pair()
  }, [code])

  return (
    <section className="griffin-control-deck griffin-pairing-deck mx-auto flex w-full max-w-[430px] flex-col">
      <div className="griffin-deck-header">
        <div className="griffin-deck-brand"><span className="griffin-deck-mark">G</span><div><p>GRIFFIN</p><p>MAC CONTROL INSTRUMENT</p></div></div>
        <StatusLED state="amber" label="PAIRING" />
      </div>
      <MetalPanel className="griffin-pairing-display-panel">
        <div className="hw-control-heading"><EngravedLabel>LOCAL CONTROL LINK</EngravedLabel><MonitorUp className="h-4 w-4" /></div>
        <InstrumentDisplay className="griffin-pairing-display">
          <Link2 className="h-6 w-6" />
          <h2>Put your Mac in your hand.</h2>
          <p>Start the phone remote in Griffin desktop mode, then enter the six-digit code shown on your Mac.</p>
        </InstrumentDisplay>
        <div className="griffin-pairing-status">
          <PermissionPill ok={status?.permissions.screen_recording ?? false}>Screen recording</PermissionPill>
          <PermissionPill ok={status?.permissions.accessibility ?? false}>Accessibility</PermissionPill>
        </div>
      </MetalPanel>
      <ControlGroup label="PAIR A DEVICE" meta={<span className="hw-readout">30 MIN SESSION</span>} className="griffin-pairing-control">
        <label htmlFor="pair-code">Pairing code</label>
        <Input id="pair-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} onKeyDown={(event) => event.key === "Enter" && code.length === 6 && pair()} placeholder="000000" className="griffin-pairing-input" />
        <PhysicalButton className="mt-3 w-full" disabled={busy || code.length !== 6} onClick={pair}>
          {busy ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <Laptop className="mr-2 h-4 w-4" />}
          Connect to Mac
        </PhysicalButton>
        {error && <p role="alert" className="griffin-module-note is-error">{error}</p>}
        {!status?.ready && status?.supported && <p className="griffin-module-note is-warning">Allow Screen Recording and Accessibility for your terminal app in System Settings, then restart Griffin.</p>}
      </ControlGroup>
    </section>
  )
}

function LiveRemote({ status, token, onStop }: { status: RemoteStatus; token: string; onStop: () => void }) {
  const [frameUrl, setFrameUrl] = useState<string | null>(null)
  const [frameError, setFrameError] = useState("")
  const [controlError, setControlError] = useState("")
  const [text, setText] = useState("")
  const [keyboardLive, setKeyboardLive] = useState(true)
  const [command, setCommand] = useState("")
  const [commandBusy, setCommandBusy] = useState(false)
  const [commandError, setCommandError] = useState("")
  const [commandReply, setCommandReply] = useState("")
  const [voiceState, setVoiceState] = useState<PhoneVoiceState>("idle")
  const [voiceTranscript, setVoiceTranscript] = useState("")
  const [volume, setVolume] = useState(50)
  const [volumeReady, setVolumeReady] = useState(false)
  const [volumeError, setVolumeError] = useState("")
  const [scrollSlider, setScrollSlider] = useState(0)
  const [surfaceFeedback, setSurfaceFeedback] = useState<{ id: number; label: string; x: number; y: number } | null>(null)
  const [openingSettings, setOpeningSettings] = useState(false)
  const [controlsOpen, setControlsOpen] = useState(false)
  const [controlMode, setControlMode] = useState<"pointer" | "scroll" | "window">("pointer")
  const [selectingWindow, setSelectingWindow] = useState(false)
  const [frameSize, setFrameSize] = useState({ width: 16, height: 9 })
  const [launchingApp, setLaunchingApp] = useState<RemoteApplication | null>(null)
  const [applications, setApplications] = useState<RemoteApplicationOption[]>([])
  const [appQuery, setAppQuery] = useState("")
  const [immersive, setImmersive] = useState(false)
  const [agentExpanded, setAgentExpanded] = useState(false)

  useEffect(() => {
    if (!agentExpanded) return
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setAgentExpanded(false)
    }
    window.addEventListener("keydown", closeOnEscape)
    return () => window.removeEventListener("keydown", closeOnEscape)
  }, [agentExpanded])
  const remoteRef = useRef<HTMLElement>(null)
  const gesture = useRef<{
    pointerId: number
    x: number
    y: number
    lastX: number
    lastY: number
    moved: boolean
    longPressed: boolean
    scrollSent: boolean
  } | null>(null)
  const activePointers = useRef(new Map<number, { x: number; y: number }>())
  const twoFingerCenter = useRef<{ x: number; y: number } | null>(null)
  const longPressTimer = useRef<number | null>(null)
  const tapTimer = useRef<number | null>(null)
  const pointerPosition = useRef({ x: 0.5, y: 0.5 })
  const lastMoveAt = useRef(0)
  const scrollSliderValue = useRef(0)
  const windowMovePending = useRef({ dx: 0, dy: 0 })
  const windowMoveSending = useRef(false)
  const windowMoveGeneration = useRef(0)
  const windowRelease = useRef<Promise<boolean> | null>(null)
  const windowSelected = useRef(false)
  const feedbackTimer = useRef<number | null>(null)
  const volumeTimer = useRef<number | null>(null)
  const voiceTimer = useRef<number | null>(null)
  const voiceRecorder = useRef<MediaRecorder | null>(null)
  const voiceStream = useRef<MediaStream | null>(null)
  const voiceChunks = useRef<Blob[]>([])
  const keyboardQueue = useRef<Promise<void>>(Promise.resolve())

  const send = useCallback(async (input: RemoteInput) => {
    try {
      await sendRemoteInput(token, input)
      setControlError("")
      return true
    } catch (reason) {
      setControlError(reason instanceof Error ? reason.message : "Mac control failed")
      return false
    }
  }, [token])

  const clampScroll = (value: number) => {
    const rounded = Math.max(-100, Math.min(100, Math.round(value)))
    return Object.is(rounded, -0) ? 0 : rounded
  }

  const moveScrollSlider = (nextValue: number) => {
    const delta = nextValue - scrollSliderValue.current
    scrollSliderValue.current = nextValue
    setScrollSlider(nextValue)
    if (delta) void send({ type: "scroll", dx: 0, dy: clampScroll(delta * 2) })
  }

  const releaseScrollSlider = () => {
    scrollSliderValue.current = 0
    setScrollSlider(0)
  }

  const showSurfaceFeedback = (label: string, point: { x: number; y: number }) => {
    if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current)
    setSurfaceFeedback({ id: Date.now(), label, ...point })
    feedbackTimer.current = window.setTimeout(() => setSurfaceFeedback(null), 520)
  }

  const queueKeyboardInputs = (inputs: RemoteInput[]) => {
    keyboardQueue.current = keyboardQueue.current.then(async () => {
      setKeyboardLive(false)
      for (const input of inputs) await send(input)
      setKeyboardLive(true)
    })
  }

  const streamTextChange = (nextText: string) => {
    const previous = Array.from(text)
    const next = Array.from(nextText)
    let prefix = 0
    while (prefix < previous.length && prefix < next.length && previous[prefix] === next[prefix]) prefix += 1
    let suffix = 0
    while (
      suffix < previous.length - prefix &&
      suffix < next.length - prefix &&
      previous[previous.length - 1 - suffix] === next[next.length - 1 - suffix]
    ) suffix += 1

    const inputs: RemoteInput[] = []
    for (let index = 0; index < suffix; index += 1) inputs.push({ type: "key", key: "left" })
    for (let index = prefix; index < previous.length - suffix; index += 1) inputs.push({ type: "key", key: "backspace" })
    const inserted = next.slice(prefix, next.length - suffix).join("")
    if (inserted) inputs.push({ type: "text", text: inserted })
    for (let index = 0; index < suffix; index += 1) inputs.push({ type: "key", key: "right" })

    setText(nextText)
    if (inputs.length) queueKeyboardInputs(inputs)
  }

  const submitCommand = async () => {
    const message = command.trim()
    if (!message || commandBusy || voiceState !== "idle") return
    setCommandBusy(true)
    setCommandError("")
    try {
      const response = await sendRemoteCommand(
        token,
        message,
        sessionStorage.getItem(CHAT_SESSION_KEY),
      )
      sessionStorage.setItem(CHAT_SESSION_KEY, response.session_id)
      setCommandReply(response.response)
      setCommand("")
    } catch (reason) {
      setCommandError(reason instanceof Error ? reason.message : "Griffin could not run that command.")
    } finally {
      setCommandBusy(false)
    }
  }

  const submitVoiceCommand = async (audio: Blob) => {
    if (!audio.size) {
      setCommandError("No audio was recorded. Please try again.")
      setVoiceState("idle")
      return
    }
    setVoiceState("transcribing")
    setCommandError("")
    try {
      const response = await sendRemoteVoice(
        token,
        audio,
        sessionStorage.getItem(CHAT_SESSION_KEY),
      )
      sessionStorage.setItem(CHAT_SESSION_KEY, response.session_id)
      setVoiceTranscript(response.transcript)
      setCommandReply(response.response)
    } catch (reason) {
      setCommandError(reason instanceof Error ? reason.message : "Griffin could not understand that recording.")
    } finally {
      setVoiceState("idle")
    }
  }

  const stopVoiceRecording = () => {
    if (voiceTimer.current !== null) window.clearTimeout(voiceTimer.current)
    voiceTimer.current = null
    if (voiceRecorder.current?.state === "recording") voiceRecorder.current.stop()
  }

  const toggleVoiceRecording = async () => {
    if (voiceState === "listening") {
      stopVoiceRecording()
      return
    }
    if (voiceState !== "idle") return
    setCommandError("")
    setVoiceTranscript("")
    if (window.isSecureContext === false) {
      setCommandError("Live microphone access on iPhone requires Griffin to be opened over trusted HTTPS.")
      return
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setCommandError("This phone browser does not support live microphone recording.")
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: false,
      })
      if (stream.getVideoTracks().length) {
        stream.getTracks().forEach((track) => track.stop())
        setCommandError("Griffin refused a camera stream. Microphone audio is required.")
        return
      }
      const recorder = new MediaRecorder(stream)
      voiceStream.current = stream
      voiceRecorder.current = recorder
      voiceChunks.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size) voiceChunks.current.push(event.data)
      }
      recorder.onerror = () => {
        stream.getTracks().forEach((track) => track.stop())
        setCommandError("Phone microphone recording stopped unexpectedly.")
        setVoiceState("idle")
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        voiceStream.current = null
        voiceRecorder.current = null
        if (voiceTimer.current !== null) window.clearTimeout(voiceTimer.current)
        voiceTimer.current = null
        void submitVoiceCommand(new Blob(voiceChunks.current, { type: recorder.mimeType || "audio/webm" }))
      }
      recorder.start()
      setVoiceState("listening")
      voiceTimer.current = window.setTimeout(stopVoiceRecording, MAX_VOICE_RECORDING_MS)
    } catch (reason) {
      setVoiceState("idle")
      setCommandError(reason instanceof Error && reason.name === "NotAllowedError"
        ? "Microphone permission was denied. Allow microphone access in your phone browser settings."
        : "Griffin could not access this phone's microphone.")
    }
  }

  const changeVolume = (nextVolume: number) => {
    setVolume(nextVolume)
    setVolumeError("")
    if (volumeTimer.current !== null) window.clearTimeout(volumeTimer.current)
    volumeTimer.current = window.setTimeout(async () => {
      volumeTimer.current = null
      const changed = await send({ type: "volume", volume: nextVolume })
      if (!changed) setVolumeError("Could not change the Mac volume.")
    }, 100)
  }

  const openAccessibility = async () => {
    setOpeningSettings(true)
    try {
      await openRemoteAccessibilitySettings(token)
      setControlError("Accessibility Settings opened on your Mac. Enable the listed Python runtime, then restart Griffin.")
    } catch (reason) {
      setControlError(reason instanceof Error ? reason.message : "Could not open Accessibility Settings on the Mac.")
    } finally {
      setOpeningSettings(false)
    }
  }

  const launchApp = async (app: RemoteApplication) => {
    setLaunchingApp(app)
    setControlError("")
    try {
      await launchRemoteApplication(token, app)
    } catch (reason) {
      setControlError(reason instanceof Error ? reason.message : "Could not open the application.")
    } finally {
      setLaunchingApp(null)
    }
  }

  useEffect(() => {
    let cancelled = false
    getRemoteVolume(token)
      .then(({ volume: currentVolume }) => {
        if (!cancelled) { setVolume(currentVolume); setVolumeReady(true); setVolumeError("") }
      })
      .catch(() => { if (!cancelled) setVolumeError("Mac volume is unavailable.") })
    return () => { cancelled = true }
  }, [token])

  useEffect(() => {
    let cancelled = false
    getRemoteApplications(token)
      .then(({ applications: installed }) => { if (!cancelled) setApplications(installed) })
      .catch((reason) => { if (!cancelled) setControlError(reason instanceof Error ? reason.message : "Could not load Mac applications.") })
    return () => { cancelled = true }
  }, [token])

  useEffect(() => {
    let cancelled = false
    let currentUrl: string | null = null
    const load = async () => {
      try {
        const blob = await getRemoteFrame(token)
        if (cancelled) return
        const nextUrl = URL.createObjectURL(blob)
        if (currentUrl) URL.revokeObjectURL(currentUrl)
        currentUrl = nextUrl
        setFrameUrl(nextUrl)
        setFrameError("")
      } catch (reason) {
        if (!cancelled) setFrameError(reason instanceof Error ? reason.message : "Screen unavailable")
      }
    }
    void load()
    const timer = window.setInterval(load, 850)
    return () => { cancelled = true; window.clearInterval(timer); if (currentUrl) URL.revokeObjectURL(currentUrl) }
  }, [token])

  useEffect(() => {
    const syncFullscreen = () => {
      if (document.fullscreenElement === null && document.fullscreenEnabled) setImmersive(false)
    }
    document.addEventListener("fullscreenchange", syncFullscreen)
    return () => {
      document.removeEventListener("fullscreenchange", syncFullscreen)
      if (longPressTimer.current !== null) window.clearTimeout(longPressTimer.current)
      if (tapTimer.current !== null) window.clearTimeout(tapTimer.current)
      if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current)
      if (volumeTimer.current !== null) window.clearTimeout(volumeTimer.current)
      if (voiceTimer.current !== null) window.clearTimeout(voiceTimer.current)
      if (voiceRecorder.current) voiceRecorder.current.onstop = null
      if (voiceRecorder.current?.state === "recording") voiceRecorder.current.stop()
      voiceStream.current?.getTracks().forEach((track) => track.stop())
      windowMoveGeneration.current += 1
      windowMovePending.current = { dx: 0, dy: 0 }
      if (windowSelected.current) void send({ type: "release_window" })
    }
  }, [])

  const clearLongPress = () => {
    if (longPressTimer.current !== null) window.clearTimeout(longPressTimer.current)
    longPressTimer.current = null
  }

  const toggleImmersive = async () => {
    if (immersive) {
      if (document.fullscreenElement) await document.exitFullscreen?.().catch(() => undefined)
      const orientation = screen.orientation as ScreenOrientation & { unlock?: () => void }
      orientation?.unlock?.()
      setImmersive(false)
      return
    }
    setImmersive(true)
    await remoteRef.current?.requestFullscreen?.().catch(() => undefined)
    const orientation = screen.orientation as ScreenOrientation & { lock?: (orientation: string) => Promise<void> }
    await orientation?.lock?.("landscape").catch(() => undefined)
  }

  const normalizedPoint = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const imageAspect = frameSize.width / frameSize.height
    const containerAspect = rect.width / rect.height
    let renderedWidth = rect.width
    let renderedHeight = rect.height
    let offsetX = 0
    let offsetY = 0
    if (containerAspect > imageAspect) {
      renderedWidth = rect.height * imageAspect
      offsetX = (rect.width - renderedWidth) / 2
    } else {
      renderedHeight = rect.width / imageAspect
      offsetY = (rect.height - renderedHeight) / 2
    }
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left - offsetX) / renderedWidth)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top - offsetY) / renderedHeight)),
    }
  }

  const activateWindowMove = async () => {
    if (selectingWindow) return
    setSelectingWindow(true)
    await windowRelease.current
    const selected = await send({ type: "select_window" })
    windowSelected.current = selected
    setSelectingWindow(false)
    setControlMode(selected ? "window" : "pointer")
  }

  const flushWindowMove = async (generation: number) => {
    if (windowMoveSending.current) return
    windowMoveSending.current = true
    try {
      while (generation === windowMoveGeneration.current) {
        const dx = clampScroll(windowMovePending.current.dx)
        const dy = clampScroll(windowMovePending.current.dy)
        if (!dx && !dy) break
        windowMovePending.current.dx -= dx
        windowMovePending.current.dy -= dy
        if (!await send({ type: "move_window", dx, dy })) {
          windowMovePending.current = { dx: 0, dy: 0 }
          break
        }
      }
    } finally {
      windowMoveSending.current = false
      const { dx, dy } = windowMovePending.current
      if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
        void flushWindowMove(windowMoveGeneration.current)
      }
    }
  }

  const queueWindowMove = (dx: number, dy: number) => {
    windowMovePending.current.dx += dx
    windowMovePending.current.dy += dy
    void flushWindowMove(windowMoveGeneration.current)
  }

  const switchControlMode = async (nextMode: "pointer" | "scroll") => {
    if (controlMode === "window") {
      windowMoveGeneration.current += 1
      windowMovePending.current = { dx: 0, dy: 0 }
      windowSelected.current = false
      setControlMode(nextMode)
      const release = send({ type: "release_window" })
      windowRelease.current = release
      await release
      if (windowRelease.current === release) windowRelease.current = null
      return
    }
    setControlMode(nextMode)
  }

  const pointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (activePointers.current.has(event.pointerId)) activePointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    const active = gesture.current
    if (active && active.pointerId === event.pointerId && controlMode === "scroll") {
      event.preventDefault()
      const dx = event.clientX - active.lastX
      const dy = event.clientY - active.lastY
      active.lastX = event.clientX
      active.lastY = event.clientY
      if (Math.abs(event.clientX - active.x) + Math.abs(event.clientY - active.y) > 3) active.moved = true
      const scrollX = clampScroll(dx * 2)
      const scrollY = clampScroll(dy * 2)
      if (scrollX || scrollY) {
        active.scrollSent = true
        void send({ type: "scroll", dx: scrollX, dy: scrollY })
      }
      return
    }
    if (active && active.pointerId === event.pointerId && controlMode === "window") {
      event.preventDefault()
      const rect = event.currentTarget.getBoundingClientRect()
      const dx = (event.clientX - active.lastX) * (frameSize.width / rect.width)
      const dy = (event.clientY - active.lastY) * (frameSize.height / rect.height)
      active.lastX = event.clientX
      active.lastY = event.clientY
      if (Math.abs(event.clientX - active.x) + Math.abs(event.clientY - active.y) > 3) active.moved = true
      if (dx || dy) queueWindowMove(dx, dy)
      return
    }
    if (activePointers.current.size >= 2 && controlMode === "pointer") {
      clearLongPress()
      if (gesture.current) gesture.current.moved = true
      const points = [...activePointers.current.values()]
      const center = {
        x: points.reduce((total, point) => total + point.x, 0) / points.length,
        y: points.reduce((total, point) => total + point.y, 0) / points.length,
      }
      const previous = twoFingerCenter.current
      twoFingerCenter.current = center
      if (previous) {
        const dx = clampScroll(-(center.x - previous.x) * 2)
        const dy = clampScroll(-(center.y - previous.y) * 2)
        if (dx || dy) void send({ type: "scroll", dx, dy })
      }
      return
    }
    if (!active || active.pointerId !== event.pointerId || controlMode !== "pointer") return
    const distance = Math.abs(event.clientX - active.x) + Math.abs(event.clientY - active.y)
    if (distance > 6) { active.moved = true; clearLongPress() }
    const point = normalizedPoint(event)
    pointerPosition.current = point
    const now = performance.now()
    if (now - lastMoveAt.current >= 45) {
      lastMoveAt.current = now
      void send({ type: "move", ...point })
    }
  }

  const pointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    clearLongPress()
    const wasMultiTouch = activePointers.current.size >= 2
    activePointers.current.delete(event.pointerId)
    if (activePointers.current.size < 2) twoFingerCenter.current = null
    const start = gesture.current
    gesture.current = null
    if (!start || wasMultiTouch || start.pointerId !== event.pointerId || start.longPressed) return
    if (controlMode === "window") return
    if (controlMode === "scroll") {
      const finalDx = event.clientX - (start.scrollSent ? start.lastX : start.x)
      const finalDy = event.clientY - (start.scrollSent ? start.lastY : start.y)
      const scrollX = clampScroll(finalDx * 2)
      const scrollY = clampScroll(finalDy * 2)
      if (scrollX || scrollY) void send({ type: "scroll", dx: scrollX, dy: scrollY })
      return
    }
    const point = normalizedPoint(event)
    pointerPosition.current = point
    if (!start.moved) {
      if (tapTimer.current !== null) {
        window.clearTimeout(tapTimer.current)
        tapTimer.current = null
        showSurfaceFeedback("Double-click", point)
        void send({ type: "double_tap", ...point })
      } else {
        tapTimer.current = window.setTimeout(() => {
          tapTimer.current = null
          showSurfaceFeedback("Click", point)
          void send({ type: "tap", ...point })
        }, 240)
      }
    }
  }

  const pointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    activePointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    event.currentTarget.setPointerCapture?.(event.pointerId)
    if (activePointers.current.size >= 2) {
      clearLongPress()
      if (gesture.current) gesture.current.moved = true
      const points = [...activePointers.current.values()]
      twoFingerCenter.current = {
        x: points.reduce((total, point) => total + point.x, 0) / points.length,
        y: points.reduce((total, point) => total + point.y, 0) / points.length,
      }
      return
    }
    gesture.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      moved: false,
      longPressed: false,
      scrollSent: false,
    }
    if (controlMode === "pointer") {
      const point = normalizedPoint(event)
      longPressTimer.current = window.setTimeout(() => {
        if (!gesture.current || gesture.current.moved || gesture.current.pointerId !== event.pointerId) return
        gesture.current.longPressed = true
        pointerPosition.current = point
        void send({ type: "secondary_tap", ...point })
      }, 550)
    }
  }

  const cancelPointer = (event: React.PointerEvent<HTMLDivElement>) => {
    clearLongPress()
    activePointers.current.delete(event.pointerId)
    twoFingerCenter.current = null
    gesture.current = null
  }

  const agentState = commandError
    ? "ERROR"
    : voiceState === "listening"
      ? "LISTENING"
      : voiceState === "transcribing" || commandBusy
        ? "THINKING"
        : commandReply
          ? "DONE"
          : "IDLE"
  const agentLed = commandError ? "red" : voiceState === "listening" || voiceState === "transcribing" || commandBusy ? "amber" : "cyan"

  return (
    <section ref={remoteRef} className={cn("griffin-control-deck mx-auto flex w-full max-w-[430px] flex-col", immersive && "remote-immersive")}>
      <div className="remote-live-header griffin-deck-header">
        <div className="griffin-deck-brand">
          <span className="griffin-deck-mark">G</span>
          <div className="min-w-0"><p className="truncate">GRIFFIN</p><p>MAC CONTROL INSTRUMENT</p></div>
        </div>
        <div className="griffin-deck-header__actions">
          <PhysicalButton tone="metal" className="hw-icon-key" aria-label={immersive ? "Exit full screen" : "Open full screen landscape"} onClick={() => void toggleImmersive()}>
            {immersive ? <Minimize2 className="mr-1.5 h-4 w-4" /> : <Maximize2 className="mr-1.5 h-4 w-4" />}
          </PhysicalButton>
          <PhysicalButton className="hw-icon-key hw-icon-key--stop" aria-label="Stop remote session" onClick={onStop}><Power className="h-4 w-4" /></PhysicalButton>
        </div>
      </div>
      <div className="griffin-status-strip" aria-label="System status">
        <StatusLED state="green" label="MAC ONLINE" />
        <StatusLED state={status.permissions.accessibility ? "green" : "amber"} label={status.permissions.accessibility ? "CONTROL READY" : "PERMISSION"} />
        <StatusLED state={agentLed} label={`AGENT ${agentState}`} />
        <StatusLED state={frameUrl ? "cyan" : "amber"} label={frameUrl ? "STREAM LIVE" : "STREAM WAIT"} />
      </div>
      {!status.permissions.accessibility && <div className="griffin-hardware-alert">
        <p>Mirroring works, but macOS is discarding scroll and keyboard events. Enable Accessibility for Griffin’s Python runtime.</p>
        {status.permission_target && <p className="mt-1 break-all font-mono text-[10px] text-amber-100/70">{status.permission_target}</p>}
        <Button variant="outline" size="sm" className="mt-2" disabled={openingSettings} onClick={() => void openAccessibility()}>
          {openingSettings ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Settings2 className="mr-1.5 h-3.5 w-3.5" />}
          Open settings on Mac
        </Button>
      </div>}

      <div className="remote-rotate-hint">
        <RotateCcw className="h-10 w-10" />
        <p className="text-base font-semibold">Rotate your phone</p>
        <p className="max-w-xs text-center text-xs leading-5">The full remote uses landscape so the Mac screen and controls remain visible together.</p>
      </div>

      <div className="remote-immersive__layout">
        <div className="remote-screen-column">
          <MetalPanel className="remote-monitor-panel">
            <div className="remote-monitor-labels"><EngravedLabel>REMOTE DISPLAY</EngravedLabel><span>{frameSize.width}:{frameSize.height}</span></div>
            <div className="remote-display-hardware">
              <div className="remote-screen-bezel">
                <span className="remote-monitor-camera" aria-hidden="true" />
                <div className="remote-screen-mode">
                  <button aria-pressed={controlMode === "pointer"} onClick={() => void switchControlMode("pointer")} className={cn(controlMode === "pointer" && "is-active")}><MousePointer2 className="h-3 w-3" />Pointer</button>
                  <button aria-pressed={controlMode === "scroll"} onClick={() => void switchControlMode("scroll")} className={cn(controlMode === "scroll" && "is-active")}><ScrollText className="h-3 w-3" />Scroll</button>
                  <button aria-label={controlMode === "window" ? "Exit window move mode" : "Move active window"} aria-pressed={controlMode === "window"} disabled={selectingWindow} onClick={() => void (controlMode === "window" ? switchControlMode("pointer") : activateWindowMove())} className={cn(controlMode === "window" && "is-active")}><Move className={cn("h-3 w-3", selectingWindow && "animate-pulse")} />Move</button>
                </div>
                <div className="remote-stage relative overflow-hidden touch-none" style={{ aspectRatio: `${frameSize.width} / ${frameSize.height}` }}>
                  {frameUrl ? <img src={frameUrl} alt={`Live screen from ${status.device_name}`} draggable={false} onLoad={(event) => setFrameSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} className="h-full w-full object-contain" /> : <div className="grid h-full place-items-center"><RefreshCw className="h-7 w-7 animate-spin" /></div>}
                  <div aria-label="Mac trackpad surface" aria-description={controlMode === "window" ? "Drag to reposition the selected Mac window" : "Drag to move the pointer, tap to click, and double-tap to double-click"} className={cn("absolute inset-0", controlMode === "pointer" ? "cursor-crosshair" : controlMode === "window" ? "cursor-move ring-2 ring-inset ring-emerald-300/70" : "cursor-ns-resize")} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={cancelPointer} onWheel={(event) => { event.preventDefault(); void send({ type: "scroll", dx: clampScroll(-event.deltaX), dy: clampScroll(-event.deltaY) }) }} />
                  {surfaceFeedback && <span key={surfaceFeedback.id} role="status" className="remote-tap-feedback" style={{ left: `${surfaceFeedback.x * 100}%`, top: `${surfaceFeedback.y * 100}%` }}><span className="remote-tap-feedback__ring" /><span className="remote-tap-feedback__label">{surfaceFeedback.label}</span></span>}
                  {controlMode === "pointer" && <span className="remote-pointer-hint">Tap to click / Double-tap to open</span>}
                  {controlMode === "window" && <span className="remote-pointer-hint">Drag to move the selected window</span>}
                  <div className="remote-scroll-tab" aria-label="Window scroll control">
                    <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                    <input aria-label="Scroll active Mac window" className="remote-scroll-slider" type="range" min={-100} max={100} step={2} value={scrollSlider} onChange={(event) => moveScrollSlider(Number(event.currentTarget.value))} onPointerUp={releaseScrollSlider} onPointerCancel={releaseScrollSlider} onTouchEnd={releaseScrollSlider} onBlur={releaseScrollSlider} />
                    <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Scroll</span>
                  </div>
                </div>
                <div className="remote-monitor-chin" aria-hidden="true"><span></span></div>
              </div>
              <div className="remote-monitor-stand" aria-hidden="true"><span /></div>
            </div>
          </MetalPanel>
        </div>

        <div className="remote-control-rail">
          <MetalPanel className={cn("griffin-agent-module", agentExpanded && "is-expanded")}>
            <div className="hw-control-heading">
              <EngravedLabel>ASK GRIFFIN</EngravedLabel>
              <div className="griffin-agent-heading__tools">
                <StatusLED state={agentLed} label={agentState} />
                <button type="button" className="griffin-terminal-expand" aria-label={agentExpanded ? "Collapse Griffin response" : "Expand Griffin response"} aria-pressed={agentExpanded} onClick={() => setAgentExpanded((value) => !value)}>
                  {agentExpanded ? <Minimize2 aria-hidden /> : <Maximize2 aria-hidden />}
                  <span>{agentExpanded ? "Collapse" : "Expand"}</span>
                </button>
              </div>
            </div>
            <InstrumentDisplay className="griffin-agent-display">
              {commandReply ? <div className="griffin-terminal-response" role="status" aria-label="Griffin response">{voiceTranscript && <p className="griffin-terminal-meta">Heard: {voiceTranscript}</p>}<p>{commandReply}</p></div> : <p className="griffin-terminal-idle">&gt; AGENT ONLINE<br />&gt; AWAITING INSTRUCTION</p>}
            </InstrumentDisplay>
            <div className="griffin-command-entry">
              <Input
                aria-label="Message Griffin from phone"
                value={command}
                inputMode="text"
                enterKeyHint="send"
                autoCapitalize="sentences"
                spellCheck
                disabled={commandBusy || voiceState !== "idle"}
                onChange={(event) => { setCommand(event.target.value); setCommandError("") }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && command.trim()) {
                    event.preventDefault()
                    void submitCommand()
                  }
                }}
                placeholder="Tell Griffin what to do..."
                className="griffin-terminal-input"
              />
              <PhysicalButton tone="metal" className="hw-square-key" aria-label="Send command to Griffin" disabled={!command.trim() || commandBusy || voiceState !== "idle"} onClick={() => void submitCommand()}>
                {commandBusy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
              </PhysicalButton>
              <PhysicalButton
                tone={voiceState === "listening" ? "amber" : "dark"}
                className="hw-square-key"
                aria-label={voiceState === "listening" ? "Stop phone voice command" : "Start phone voice command"}
                aria-pressed={voiceState === "listening"}
                disabled={voiceState === "transcribing" || commandBusy}
                onClick={() => void toggleVoiceRecording()}
              >
                {voiceState === "transcribing" ? <RefreshCw className="h-4 w-4 animate-spin" /> : voiceState === "listening" ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </PhysicalButton>
            </div>
            {voiceState === "listening" && <p role="status" className="griffin-module-note is-listening">Listening on this phone. Press MIC to stop.</p>}
            {voiceState === "transcribing" && <p role="status" className="griffin-module-note">Transcribing locally and asking Griffin...</p>}
            {window.isSecureContext === false && voiceState === "idle" && <p className="griffin-module-note is-warning">Live microphone control requires a trusted HTTPS phone link.</p>}
            {commandError && <p role="alert" className="griffin-module-note is-error">{commandError}</p>}
          </MetalPanel>

          <ControlGroup label="MAC VOLUME" meta={<span aria-live="polite" className="hw-readout">{volumeReady ? `${volume}%` : "LOADING"}</span>} className="griffin-volume-module">
            <div className="griffin-volume-control">
              <VolumeX className="h-4 w-4" aria-hidden="true" />
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={volume}
                disabled={!volumeReady}
                aria-label="Mac output volume"
                onChange={(event) => changeVolume(Number(event.currentTarget.value))}
                className="griffin-volume-slider"
              />
              <div aria-hidden className="griffin-volume-knob" style={{ transform: `rotate(${-135 + volume * 2.7}deg)` }}><span /></div>
            </div>
            {volumeError && <p role="alert" className="griffin-module-note is-warning">{volumeError}</p>}
          </ControlGroup>

          <WoodPanel className="griffin-launcher">
            <div className="hw-control-heading"><EngravedLabel>OPEN ON YOUR MAC</EngravedLabel><span className="hw-launcher-mark">{applications.length} APPS</span></div>
            <Input aria-label="Find a Mac application" value={appQuery} onChange={(event) => setAppQuery(event.target.value)} placeholder="Find an application…" className="mb-2 griffin-hardware-input" />
            <div className="griffin-app-grid">
              {applications.filter(({ name }) => name.toLowerCase().includes(appQuery.trim().toLowerCase())).slice(0, 12).map(({ id, name }) => (
                <button key={id} disabled={launchingApp !== null} onClick={() => void launchApp(id)} aria-label={`Open ${name}`} className="griffin-app-key text-slate-200 bg-slate-400/10 border-slate-300/20">
                  <span>{launchingApp === id ? <RefreshCw className="h-4 w-4 animate-spin" /> : <SquareTerminal className="h-4 w-4" />}</span>
                  <strong>{name}</strong>
                </button>
              ))}
            </div>
          </WoodPanel>

          <ControlGroup label="REMOTE KEYBOARD" className="griffin-keyboard-module">
            <div className="griffin-keyboard-entry">
              <PhysicalButton tone="metal" className="hw-square-key" aria-label="Toggle keyboard controls" onClick={() => setControlsOpen((value) => !value)}><Keyboard className="h-5 w-5" /></PhysicalButton>
              <Input
                value={text}
                inputMode="text"
                enterKeyHint="send"
                autoCapitalize="sentences"
                spellCheck
                onChange={(event) => streamTextChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    queueKeyboardInputs([{ type: "key", key: "enter" }])
                  }
                }}
                placeholder="Live typing into the Mac…"
                className="griffin-hardware-input"
              />
              <PhysicalButton tone="metal" aria-label="Delete last character" disabled={!text} onClick={() => streamTextChange(Array.from(text).slice(0, -1).join(""))}>Delete</PhysicalButton>
            </div>
            <p aria-live="polite" className={cn("griffin-module-note", keyboardLive && "is-success")}>{keyboardLive ? "Keyboard live — every edit is sent immediately" : "Sending keystroke…"}</p>
            {controlsOpen && <RecessedPanel className="griffin-key-cluster">
              <Button variant="outline" size="sm" onClick={() => void send({ type: "key", key: "escape" })}>esc</Button>
              <Button variant="outline" size="icon" aria-label="Command Enter" onClick={() => void send({ type: "key", key: "enter", modifiers: ["command"] })}><Command className="h-4 w-4" /></Button>
              <Button variant="outline" size="icon" aria-label="Arrow left" onClick={() => void send({ type: "key", key: "left" })}><ArrowLeft className="h-4 w-4" /></Button>
              <Button variant="outline" size="icon" aria-label="Arrow up" onClick={() => void send({ type: "key", key: "up" })}><ArrowUp className="h-4 w-4" /></Button>
              <Button variant="outline" size="icon" aria-label="Arrow down" onClick={() => void send({ type: "key", key: "down" })}><ArrowDown className="h-4 w-4" /></Button>
              <Button variant="outline" size="icon" aria-label="Arrow right" onClick={() => void send({ type: "key", key: "right" })}><ArrowRight className="h-4 w-4" /></Button>
              <Button variant="outline" size="sm" onClick={() => void send({ type: "key", key: "enter" })}>return</Button>
            </RecessedPanel>}
          </ControlGroup>
          <ControlGroup label="FOCUSED WINDOW" meta={<span className="hw-launcher-mark">DISPLAY</span>} className="griffin-window-module">
            <div className="griffin-window-controls">
              <PhysicalButton aria-label="Put focused window in full screen" onClick={() => void send({ type: "enter_fullscreen" })}>
                <Maximize2 className="mr-1.5 h-4 w-4" />Full screen
              </PhysicalButton>
              <PhysicalButton aria-label="Take focused window out of full screen" onClick={() => void send({ type: "exit_fullscreen" })}>
                <Minimize2 className="mr-1.5 h-4 w-4" />Exit full screen
              </PhysicalButton>
            </div>
          </ControlGroup>
          <p className="griffin-instruction-plate">TAP CLICK / DOUBLE-TAP OPEN / HOLD RIGHT-CLICK / TWO-FINGER SCROLL</p>
        </div>
      </div>
      {(controlError || frameError) && <p role="alert" className="griffin-hardware-alert">{controlError || frameError}</p>}
    </section>
  )
}

export function RemoteCockpit() {
  const [status, setStatus] = useState<RemoteStatus | null>(null)
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY))

  useEffect(() => { getRemoteStatus().then(setStatus).catch(() => setStatus(null)) }, [])
  const update = (next: RemoteStatus, nextToken?: string) => {
    setStatus(next)
    if (nextToken) { sessionStorage.setItem(TOKEN_KEY, nextToken); setToken(nextToken) }
  }
  const stop = async () => {
    try { await stopRemoteSession(token) } finally { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(CHAT_SESSION_KEY); setToken(null); setStatus((current) => current ? { ...current, state: "idle", expires_at: null } : current) }
  }

  return (
    <main className="relative w-full flex-1 py-2">
      {status?.state === "paired" && token ? <LiveRemote status={status} token={token} onStop={stop} /> : <PairingView status={status} onStatus={update} />}
    </main>
  )
}
