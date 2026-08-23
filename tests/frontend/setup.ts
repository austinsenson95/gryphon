import "@testing-library/jest-dom/vitest"
import { vi } from "vitest"

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

/** Minimal WebSocket stand-in: never opens unless the test drives it. */
export class MockWebSocket {
  static instances: MockWebSocket[] = []

  readonly url: string
  readyState = 0
  onopen: ((ev: unknown) => void) | null = null
  onmessage: ((ev: { data: unknown }) => void) | null = null
  onclose: ((ev: unknown) => void) | null = null
  onerror: ((ev: unknown) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  close() {
    this.readyState = 3
    this.onclose?.({})
  }
}

vi.stubGlobal("WebSocket", MockWebSocket)

// jsdom does not implement PointerEvent — polyfill it on top of MouseEvent
// so pointer-init keys (clientX/clientY/pointerId) reach React handlers.
if (typeof window !== "undefined" && !("PointerEvent" in window)) {
  class PointerEventPolyfill extends MouseEvent {
    readonly pointerId: number
    readonly pointerType: string
    readonly isPrimary: boolean
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init)
      this.pointerId = init.pointerId ?? 0
      this.pointerType = init.pointerType ?? "mouse"
      this.isPrimary = init.isPrimary ?? true
    }
  }
  ;(window as unknown as Record<string, unknown>).PointerEvent =
    PointerEventPolyfill
}

/** Default fetch stub: healthy backend with an empty event log. */
vi.stubGlobal(
  "fetch",
  vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes("/api/health")) {
      return jsonResponse({
        status: "ok",
        service: "gryphon",
        version: "0.1.0",
        llm_mode: "mock",
      })
    }
    if (url.includes("/api/llm/provider")) {
      return jsonResponse({
        provider: "mock",
        mode: "mock",
        available: ["ollama", "xai"],
      })
    }
    if (url.includes("/api/browser")) {
      return jsonResponse({
        active: false,
        mock: true,
        url: null,
        title: null,
      })
    }
    if (url.includes("/api/events")) return jsonResponse([])
    return jsonResponse({ error: { code: "not_found", message: "not found" } }, 404)
  }),
)
