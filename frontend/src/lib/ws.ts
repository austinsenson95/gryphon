import {
  EVENT_TYPES,
  type ConnectionStatus,
  type GryphonEvent,
} from "@/lib/types"
import { API_BASE } from "@/lib/api"

const MIN_BACKOFF_MS = 1_000
const MAX_BACKOFF_MS = 15_000

/**
 * WS endpoint derived from the same base as the REST client so a
 * VITE_API_BASE override (non-default port/host) applies to both.
 */
export function getWebSocketUrl(): string {
  const url = new URL(API_BASE)
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return `${url.origin}/ws`
}

/**
 * Validate and normalize a raw WS payload into the event envelope
 * defined by SPEC §2. Returns null for non-envelope frames
 * (e.g. the {"type":"CONNECTED"} hello) and malformed payloads.
 */
export function parseEvent(raw: unknown): GryphonEvent | null {
  if (typeof raw === "string") {
    try {
      raw = JSON.parse(raw)
    } catch {
      return null
    }
  }
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null
  const evt = raw as Record<string, unknown>
  if (
    typeof evt.id !== "string" ||
    typeof evt.type !== "string" ||
    typeof evt.timestamp !== "string"
  ) {
    return null
  }
  if (!(EVENT_TYPES as readonly string[]).includes(evt.type)) return null
  return {
    id: evt.id,
    type: evt.type as GryphonEvent["type"],
    timestamp: evt.timestamp,
    session_id: typeof evt.session_id === "string" ? evt.session_id : null,
    task_id: typeof evt.task_id === "string" ? evt.task_id : null,
    data:
      evt.data !== null && typeof evt.data === "object" && !Array.isArray(evt.data)
        ? (evt.data as Record<string, unknown>)
        : {},
  }
}

export interface GryphonSocketHandlers {
  onEvent?: (event: GryphonEvent) => void
  onStatus?: (status: ConnectionStatus) => void
}

export interface GryphonSocket {
  close: () => void
}

/**
 * WebSocket client with exponential-backoff reconnect (1s -> 15s max).
 * The backend sends a {"type":"CONNECTED"} hello plus a replay of recent
 * events on connect; every replayed frame is parsed as an event envelope.
 */
export function createGryphonSocket(
  handlers: GryphonSocketHandlers,
  url: string = getWebSocketUrl(),
): GryphonSocket {
  let ws: WebSocket | null = null
  let backoff = MIN_BACKOFF_MS
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let intentionallyClosed = false

  const setStatus = (status: ConnectionStatus) => handlers.onStatus?.(status)

  function connect() {
    setStatus(backoff === MIN_BACKOFF_MS ? "connecting" : "reconnecting")
    ws = new WebSocket(url)

    ws.onopen = () => {
      backoff = MIN_BACKOFF_MS
      setStatus("open")
    }

    ws.onmessage = (msg: MessageEvent) => {
      const event = parseEvent(msg.data)
      if (event) handlers.onEvent?.(event)
    }

    ws.onclose = () => {
      if (intentionallyClosed) {
        setStatus("closed")
        return
      }
      setStatus("reconnecting")
      reconnectTimer = setTimeout(() => {
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS)
        connect()
      }, backoff)
    }

    ws.onerror = () => {
      // onclose handles the reconnect path
      ws?.close()
    }
  }

  connect()

  return {
    close() {
      intentionallyClosed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    },
  }
}
