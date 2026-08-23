import { useCallback, useEffect, useRef, useState } from "react"
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ChevronDown,
  ChevronUp,
  Command,
  Code2,
  Keyboard,
  Laptop,
  Link2,
  LockKeyhole,
  Maximize2,
  Minimize2,
  MousePointer2,
  MousePointerClick,
  MonitorUp,
  Music2,
  NotebookPen,
  Power,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  getRemoteFrame,
  getRemoteStatus,
  launchRemoteApplication,
  openRemoteAccessibilitySettings,
  pairRemote,
  sendRemoteInput,
  stopRemoteSession,
} from "@/lib/api"
import type { RemoteApplication, RemoteInput, RemoteStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

const TOKEN_KEY = "griffin.remote.token"

const REMOTE_APPS: Array<{
  id: RemoteApplication
  label: string
  icon: typeof Sparkles
  tone: string
}> = [
  { id: "hermes", label: "Hermes", icon: Sparkles, tone: "text-violet-200 bg-violet-400/10 border-violet-300/20" },
  { id: "spotify", label: "Spotify", icon: Music2, tone: "text-emerald-200 bg-emerald-400/10 border-emerald-300/20" },
  { id: "notes", label: "Notes", icon: NotebookPen, tone: "text-amber-100 bg-amber-300/10 border-amber-200/20" },
  { id: "vscode", label: "VS Code", icon: Code2, tone: "text-cyan-200 bg-cyan-400/10 border-cyan-300/20" },
  { id: "terminal", label: "Terminal", icon: SquareTerminal, tone: "text-slate-200 bg-slate-400/10 border-slate-300/20" },
]

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

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-5 lg:grid-cols-[1.1fr_.9fr]">
      <section className="remote-stage flex min-h-[420px] flex-col justify-between rounded-[2rem] border border-cyan-200/15 bg-[#07111f]/85 p-6 shadow-2xl shadow-black/30 sm:p-8">
        <div>
          <div className="mb-8 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-[0.28em] text-cyan-200/65">Local control link</span>
            <span className="h-2 w-2 rounded-full bg-amber-300 shadow-[0_0_12px_rgba(252,211,77,.8)]" />
          </div>
          <MonitorUp className="mb-5 h-11 w-11 text-cyan-200" strokeWidth={1.4} />
          <h2 className="max-w-lg text-3xl font-semibold leading-tight text-white sm:text-4xl">Put your Mac in your hand.</h2>
          <p className="mt-4 max-w-xl text-sm leading-6 text-slate-300">On your Mac, switch Griffin to Desktop mode and start the phone remote. Enter the six-digit code shown there.</p>
        </div>
        <div className="mt-8 flex flex-wrap gap-2">
          <PermissionPill ok={status?.permissions.screen_recording ?? false}>Screen recording</PermissionPill>
          <PermissionPill ok={status?.permissions.accessibility ?? false}>Accessibility</PermissionPill>
        </div>
      </section>

      <section className="rounded-[2rem] border border-white/10 bg-slate-950/70 p-6 backdrop-blur-xl sm:p-8">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-2xl bg-amber-300 text-slate-950"><Link2 className="h-5 w-5" /></div>
          <div><p className="font-semibold text-white">Pair a device</p><p className="text-xs text-slate-400">One remote at a time · 30 minute session</p></div>
        </div>

        <div className="my-6 flex items-center gap-3 text-[10px] uppercase tracking-[.2em] text-slate-500"><span className="h-px flex-1 bg-white/10" />Code from your Mac<span className="h-px flex-1 bg-white/10" /></div>
        <label htmlFor="pair-code" className="text-xs font-medium text-slate-300">Pairing code</label>
        <Input
          id="pair-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
          onKeyDown={(event) => event.key === "Enter" && code.length === 6 && pair()}
          placeholder="000000"
          className="mt-2 h-14 text-center font-mono text-2xl tracking-[.3em]"
        />
        <Button className="mt-3 w-full" disabled={busy || code.length !== 6} onClick={pair}>
          {busy ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <Laptop className="mr-2 h-4 w-4" />}
          Connect to Mac
        </Button>
        {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
        {!status?.ready && status?.supported && <p className="mt-5 text-xs leading-5 text-amber-100/75">Allow Screen Recording and Accessibility for your terminal app in System Settings → Privacy &amp; Security, then restart Griffin.</p>}
      </section>
    </div>
  )
}

function LiveRemote({ status, token, onStop }: { status: RemoteStatus; token: string; onStop: () => void }) {
  const [frameUrl, setFrameUrl] = useState<string | null>(null)
  const [frameError, setFrameError] = useState("")
  const [controlError, setControlError] = useState("")
  const [text, setText] = useState("")
  const [sendingText, setSendingText] = useState(false)
  const [textDelivered, setTextDelivered] = useState(false)
  const [scrollSlider, setScrollSlider] = useState(0)
  const [surfaceFeedback, setSurfaceFeedback] = useState<{ id: number; label: string; x: number; y: number } | null>(null)
  const [openingSettings, setOpeningSettings] = useState(false)
  const [controlsOpen, setControlsOpen] = useState(false)
  const [controlMode, setControlMode] = useState<"pointer" | "scroll">("pointer")
  const [frameSize, setFrameSize] = useState({ width: 16, height: 9 })
  const [launchingApp, setLaunchingApp] = useState<RemoteApplication | null>(null)
  const [immersive, setImmersive] = useState(false)
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
  const feedbackTimer = useRef<number | null>(null)

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

  const submitText = async () => {
    if (!text || sendingText) return
    const payload = text
    setSendingText(true)
    setTextDelivered(false)
    const delivered = await send({ type: "text", text: payload })
    if (delivered) {
      setText("")
      setTextDelivered(true)
      window.setTimeout(() => setTextDelivered(false), 1400)
    }
    setSendingText(false)
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

  return (
    <section ref={remoteRef} className={cn("mx-auto flex w-full max-w-6xl flex-col gap-3", immersive && "remote-immersive")}>
      <div className="remote-live-header flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 backdrop-blur-xl">
        <div className="flex min-w-0 items-center gap-3"><span className="h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,.8)]" /><div className="min-w-0"><p className="truncate text-sm font-semibold text-white">{status.device_name}</p><p className="text-[10px] uppercase tracking-[.18em] text-emerald-200/70">Direct · Local Wi-Fi</p><p className={cn("mt-0.5 text-[9px] font-semibold uppercase tracking-[.12em]", status.permissions.accessibility ? "text-cyan-200/70" : "text-amber-200")}>{status.permissions.accessibility ? "Control enabled" : "Accessibility permission needed"}</p></div></div>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="ghost" size="sm" aria-label={immersive ? "Exit full screen" : "Open full screen landscape"} onClick={() => void toggleImmersive()}>
            {immersive ? <Minimize2 className="mr-1.5 h-4 w-4" /> : <Maximize2 className="mr-1.5 h-4 w-4" />}
            <span className="hidden sm:inline">{immersive ? "Exit" : "Full screen"}</span>
          </Button>
          <Button variant="ghost" size="sm" className="text-red-200 hover:text-red-100" onClick={onStop}><Power className="mr-1.5 h-4 w-4" />Stop</Button>
        </div>
      </div>
      {!status.permissions.accessibility && <div className="rounded-xl border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100">
        <p>Mirroring works, but macOS is discarding scroll and keyboard events. Enable Accessibility for Griffin’s Python runtime.</p>
        {status.permission_target && <p className="mt-1 break-all font-mono text-[10px] text-amber-100/70">{status.permission_target}</p>}
        <Button variant="outline" size="sm" className="mt-2" disabled={openingSettings} onClick={() => void openAccessibility()}>
          {openingSettings ? <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Settings2 className="mr-1.5 h-3.5 w-3.5" />}
          Open settings on Mac
        </Button>
      </div>}

      <div className="remote-rotate-hint">
        <RotateCcw className="h-10 w-10 text-cyan-200" />
        <p className="text-base font-semibold text-white">Rotate your phone</p>
        <p className="max-w-xs text-center text-xs leading-5 text-slate-400">The full remote is designed for landscape so the Mac screen and controls stay visible together.</p>
      </div>

      <div className="remote-immersive__layout">
        <div className="remote-screen-column">
          <div
            className="remote-stage relative overflow-hidden rounded-[1.4rem] border border-cyan-100/20 bg-[#02060c] shadow-2xl shadow-black/50 touch-none"
            style={{ aspectRatio: `${frameSize.width} / ${frameSize.height}` }}
          >
            <div className="absolute left-3 top-3 z-20 flex rounded-lg border border-white/10 bg-slate-950/80 p-1 backdrop-blur-md">
              <button aria-pressed={controlMode === "pointer"} onClick={() => setControlMode("pointer")} className={cn("flex h-7 items-center gap-1 rounded-md px-2 text-[10px] font-semibold", controlMode === "pointer" ? "bg-cyan-200 text-slate-950" : "text-slate-300")}><MousePointer2 className="h-3 w-3" />Pointer</button>
              <button aria-pressed={controlMode === "scroll"} onClick={() => setControlMode("scroll")} className={cn("flex h-7 items-center gap-1 rounded-md px-2 text-[10px] font-semibold", controlMode === "scroll" ? "bg-amber-300 text-slate-950" : "text-slate-300")}><ScrollText className="h-3 w-3" />Scroll</button>
            </div>
            {frameUrl ? <img src={frameUrl} alt={`Live screen from ${status.device_name}`} draggable={false} onLoad={(event) => setFrameSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} className="h-full w-full object-contain" /> : <div className="grid h-full place-items-center"><RefreshCw className="h-7 w-7 animate-spin text-cyan-200/60" /></div>}
            <div
              aria-label="Mac trackpad surface"
              aria-description="Drag to move the pointer, tap to click, and double-tap to double-click"
              className={cn("absolute inset-0", controlMode === "pointer" ? "cursor-crosshair" : "cursor-ns-resize")}
              onPointerDown={pointerDown}
              onPointerMove={pointerMove}
              onPointerUp={pointerUp}
              onPointerCancel={cancelPointer}
              onWheel={(event) => {
                event.preventDefault()
                void send({ type: "scroll", dx: clampScroll(-event.deltaX), dy: clampScroll(-event.deltaY) })
              }}
            />
            {surfaceFeedback && <span
              key={surfaceFeedback.id}
              role="status"
              className="remote-tap-feedback"
              style={{ left: `${surfaceFeedback.x * 100}%`, top: `${surfaceFeedback.y * 100}%` }}
            >
              <span className="remote-tap-feedback__ring" />
              <span className="remote-tap-feedback__label">{surfaceFeedback.label}</span>
            </span>}
            {controlMode === "pointer" && <span className="remote-pointer-hint">Tap to click · Double-tap to open</span>}
            <div className="remote-scroll-tab" aria-label="Window scroll control">
              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
              <input
                aria-label="Scroll active Mac window"
                className="remote-scroll-slider"
                type="range"
                min={-100}
                max={100}
                step={2}
                value={scrollSlider}
                onChange={(event) => moveScrollSlider(Number(event.currentTarget.value))}
                onPointerUp={releaseScrollSlider}
                onPointerCancel={releaseScrollSlider}
                onTouchEnd={releaseScrollSlider}
                onBlur={releaseScrollSlider}
              />
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Scroll</span>
            </div>
            <span className="remote-corner remote-corner--tl" /><span className="remote-corner remote-corner--tr" /><span className="remote-corner remote-corner--bl" /><span className="remote-corner remote-corner--br" />
          </div>
          <div className="remote-click-row mt-2 grid grid-cols-3 gap-2">
            <Button variant="outline" size="sm" onClick={() => void send({ type: "tap", ...pointerPosition.current })}><MousePointerClick className="mr-1.5 h-4 w-4" />Click</Button>
            <Button variant="outline" size="sm" onClick={() => void send({ type: "double_tap", ...pointerPosition.current })}>Double-click</Button>
            <Button variant="outline" size="sm" onClick={() => void send({ type: "secondary_tap", ...pointerPosition.current })}>Right-click</Button>
          </div>
        </div>

        <div className="remote-control-rail">
          <div className="rounded-[1.4rem] border border-white/10 bg-slate-950/75 p-3 backdrop-blur-xl">
            <div className="mb-3 flex items-center justify-between"><p className="text-xs font-semibold text-white">Open on your Mac</p><span className="font-mono text-[9px] uppercase tracking-[.18em] text-slate-500">Launch dock</span></div>
            <div className="grid grid-cols-5 gap-2">
              {REMOTE_APPS.map(({ id, label, icon: Icon, tone }) => (
                <button key={id} disabled={launchingApp !== null} onClick={() => void launchApp(id)} aria-label={`Open ${label}`} className="group flex min-w-0 flex-col items-center gap-1.5 rounded-xl p-1 text-center text-[9px] font-medium text-slate-300 transition hover:bg-white/[.05] disabled:opacity-50">
                  <span className={cn("grid h-10 w-10 place-items-center rounded-xl border transition-transform group-active:scale-95", tone)}>{launchingApp === id ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}</span>
                  <span className="w-full truncate">{label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-[1.4rem] border border-white/10 bg-slate-950/75 p-3 backdrop-blur-xl">
            <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
              <Button variant="ghost" size="icon" aria-label="Toggle keyboard controls" onClick={() => setControlsOpen((value) => !value)}><Keyboard className="h-5 w-5" /></Button>
              <Input
                value={text}
                inputMode="text"
                enterKeyHint="send"
                autoCapitalize="sentences"
                spellCheck
                onChange={(event) => { setText(event.target.value); setTextDelivered(false) }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && text) {
                    event.preventDefault()
                    void submitText()
                  }
                }}
                placeholder="Type into the selected Mac field…"
              />
              <Button disabled={!text || sendingText} onClick={() => void submitText()}>{sendingText ? "Sending…" : "Send"}</Button>
            </div>
            {textDelivered && <p role="status" className="mt-2 text-center text-[10px] font-semibold uppercase tracking-[.12em] text-emerald-300">Text sent to Mac</p>}
            {controlsOpen && <div className="mt-3 flex flex-wrap items-center justify-center gap-2 border-t border-white/10 pt-3">
              <Button variant="outline" size="sm" onClick={() => void send({ type: "key", key: "escape" })}>esc</Button>
              <Button variant="outline" size="icon" aria-label="Command Enter" onClick={() => void send({ type: "key", key: "enter", modifiers: ["command"] })}><Command className="h-4 w-4" /></Button>
              <Button variant="outline" size="icon" aria-label="Arrow left" onClick={() => void send({ type: "key", key: "left" })}><ArrowLeft className="h-4 w-4" /></Button>
              <Button variant="outline" size="icon" aria-label="Arrow up" onClick={() => void send({ type: "key", key: "up" })}><ArrowUp className="h-4 w-4" /></Button>
              <Button variant="outline" size="icon" aria-label="Arrow down" onClick={() => void send({ type: "key", key: "down" })}><ArrowDown className="h-4 w-4" /></Button>
              <Button variant="outline" size="icon" aria-label="Arrow right" onClick={() => void send({ type: "key", key: "right" })}><ArrowRight className="h-4 w-4" /></Button>
              <Button variant="outline" size="sm" onClick={() => void send({ type: "key", key: "enter" })}>return</Button>
            </div>}
          </div>
          <p className="rounded-xl border border-white/10 bg-white/[.03] px-3 py-2 text-center text-[10px] leading-4 tracking-[.06em] text-slate-400">Tap click · Double-tap open · Hold right-click · Two-finger scroll</p>
        </div>
      </div>
      {(controlError || frameError) && <p role="alert" className="rounded-xl border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs text-amber-100">{controlError || frameError}</p>}
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
    try { await stopRemoteSession(token) } finally { sessionStorage.removeItem(TOKEN_KEY); setToken(null); setStatus((current) => current ? { ...current, state: "idle", expires_at: null } : current) }
  }

  return (
    <main className="relative w-full flex-1 py-2">
      {status?.state === "paired" && token ? <LiveRemote status={status} token={token} onStop={stop} /> : <PairingView status={status} onStatus={update} />}
    </main>
  )
}
