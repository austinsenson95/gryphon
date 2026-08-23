import type {
  BrowserStatus,
  ChatResponse,
  GryphonEvent,
  HealthResponse,
  ProviderInfoResponse,
  VoiceResponse,
  LLMProvider,
} from "@/lib/types"

/**
 * LAN-friendly base URL: same host as the page, backend port 8000,
 * unless overridden by VITE_API_BASE at build time. No hard-coded IPs.
 */
export const API_BASE =
  import.meta.env.VITE_API_BASE ??
  `${location.protocol}//${location.hostname}:8000`

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { error?: { message?: string } }
      if (body?.error?.message) detail = body.error.message
    } catch {
      // keep the HTTP status fallback
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health")
}

export function sendChat(
  message: string,
  sessionId?: string | null,
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
  })
}

export function getEvents(limit = 50): Promise<GryphonEvent[]> {
  return request<GryphonEvent[]>(`/api/events?limit=${limit}`)
}

export function getProviderInfo(): Promise<ProviderInfoResponse> {
  return request<ProviderInfoResponse>("/api/llm/provider")
}

export function getBrowserStatus(): Promise<BrowserStatus> {
  return request<BrowserStatus>("/api/browser")
}

export function setProvider(provider: LLMProvider): Promise<ProviderInfoResponse> {
  return request<ProviderInfoResponse>("/api/llm/provider", {
    method: "POST",
    body: JSON.stringify({ provider }),
  })
}

/** Upload recorded audio for local speech-to-text + agent execution. */
export async function sendVoice(
  audio: Blob,
  sessionId?: string | null,
): Promise<VoiceResponse> {
  const headers: Record<string, string> = {
    "Content-Type": audio.type || "audio/webm",
  }
  if (sessionId) headers["X-Session-Id"] = sessionId
  const res = await fetch(`${API_BASE}/api/voice`, {
    method: "POST",
    headers,
    body: audio,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { error?: { message?: string } }
      if (body?.error?.message) detail = body.error.message
    } catch {
      // keep the HTTP status fallback
    }
    throw new Error(detail)
  }
  return (await res.json()) as VoiceResponse
}
