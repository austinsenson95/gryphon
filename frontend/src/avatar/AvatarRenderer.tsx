import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react"

import { cn } from "@/lib/utils"
import type { AvatarState } from "@/avatar/stateMachine"

export const AVATAR_POSITION_KEY = "griffin.avatar.pos"
/** Window event dispatched on avatar click so the chat panel can focus. */
export const AVATAR_ACTIVATE_EVENT = "griffin:avatar-activate"

const DRAG_THRESHOLD_PX = 5
const VIEWPORT_MARGIN_PX = 12

interface Position {
  x: number
  y: number
}

function clampPosition(pos: Position, size: number): Position {
  const maxX = Math.max(window.innerWidth - size - VIEWPORT_MARGIN_PX, 0)
  const maxY = Math.max(window.innerHeight - size - VIEWPORT_MARGIN_PX, 0)
  return {
    x: Math.min(Math.max(pos.x, VIEWPORT_MARGIN_PX), maxX),
    y: Math.min(Math.max(pos.y, VIEWPORT_MARGIN_PX), maxY),
  }
}

function defaultPosition(size: number): Position {
  if (typeof window === "undefined") return { x: 0, y: 0 }
  return clampPosition(
    {
      x: window.innerWidth - size - 48,
      y: window.innerHeight - size - 140,
    },
    size,
  )
}

function loadPosition(size: number): Position {
  try {
    const raw = window.localStorage.getItem(AVATAR_POSITION_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Position>
      if (typeof parsed.x === "number" && typeof parsed.y === "number") {
        return clampPosition({ x: parsed.x, y: parsed.y }, size)
      }
    }
  } catch {
    // corrupted storage -> fall back to default
  }
  return defaultPosition(size)
}

export interface AvatarRendererProps {
  state: AvatarState
  size?: number
}

/**
 * Presentational avatar. Receives ONLY its visual state — it knows nothing
 * about chat, tasks or activity (SPEC §3 isolation rule). Click dispatches
 * the `griffin:avatar-activate` window event; the dashboard decides what to
 * focus. Double-click recenters the avatar.
 */
export function AvatarRenderer({ state, size = 96 }: AvatarRendererProps) {
  const [position, setPosition] = useState<Position>(() => loadPosition(size))
  const [imageFailed, setImageFailed] = useState(false)
  const dragRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    originX: number
    originY: number
    dragging: boolean
  } | null>(null)

  const stateClass = `avatar--${state.toLowerCase()}`

  const recenter = useCallback(() => {
    window.localStorage.removeItem(AVATAR_POSITION_KEY)
    setPosition(defaultPosition(size))
  }, [size])

  useEffect(() => {
    const onResize = () =>
      setPosition((pos) => clampPosition(pos, size))
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [size])

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!Number.isFinite(e.clientX) || !Number.isFinite(e.clientY)) return
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      originX: position.x,
      originY: position.y,
      dragging: false,
    }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== e.pointerId) return
    if (!Number.isFinite(e.clientX) || !Number.isFinite(e.clientY)) return
    const dx = e.clientX - drag.startX
    const dy = e.clientY - drag.startY
    if (!drag.dragging && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return
    drag.dragging = true
    setPosition(clampPosition({ x: drag.originX + dx, y: drag.originY + dy }, size))
  }

  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    dragRef.current = null
    if (!drag || drag.pointerId !== e.pointerId) return
    if (drag.dragging) {
      setPosition((pos) => {
        const clamped = clampPosition(pos, size)
        try {
          window.localStorage.setItem(AVATAR_POSITION_KEY, JSON.stringify(clamped))
        } catch {
          // storage unavailable (private mode etc.) — non-fatal
        }
        return clamped
      })
    } else {
      window.dispatchEvent(new CustomEvent(AVATAR_ACTIVATE_EVENT))
    }
  }

  const onPointerCancel = () => {
    dragRef.current = null
  }

  return (
    <div
      role="button"
      aria-label={`Griffin avatar (${state.toLowerCase()})`}
      title="Drag to move · click to chat · double-click to recenter"
      className={cn("avatar fixed z-40", stateClass)}
      style={{ left: position.x, top: position.y, width: size, height: size }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onDoubleClick={recenter}
    >
      <div
        aria-hidden
        className="avatar__halo pointer-events-none absolute -inset-1.5 rounded-full border-2 border-transparent opacity-0 transition-opacity"
      />
      {imageFailed ? (
        <div
          data-testid="avatar-fallback"
          aria-hidden
          className="flex h-full w-full items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-900"
        >
          {/* Graceful companion fallback while the portrait is unavailable. */}
          <span style={{ fontSize: size * 0.5 }}>🐕</span>
        </div>
      ) : (
        <img
          src="/avatar/idle/griffin.png"
          alt="Griffin"
          draggable={false}
          className="h-full w-full rounded-full object-cover"
          onError={() => setImageFailed(true)}
        />
      )}
      {state === "THINKING" && (
        <div
          aria-hidden
          className="absolute -bottom-6 flex items-center gap-1 text-cyan-300"
        >
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-300"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
