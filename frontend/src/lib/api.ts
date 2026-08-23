import type {
  BrowserStatus,
  ChatResponse,
  GryphonEvent,
  HealthResponse,
  ProviderInfoResponse,
  VoiceResponse,
  LLMProvider,
  RemoteInput,
  RemotePairResponse,
  RemoteStatus,
  RemoteApplication,
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
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
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

export function getRemoteStatus(): Promise<RemoteStatus> {
  return request<RemoteStatus>("/api/remote")
}

export function startRemoteSession(): Promise<RemoteStatus> {
  return request<RemoteStatus>("/api/remote/session", { method: "POST" })
}

export function pairRemote(code: string): Promise<RemotePairResponse> {
  return request<RemotePairResponse>("/api/remote/pair", {
    method: "POST",
    body: JSON.stringify({ code }),
  })
}

export function stopRemoteSession(token?: string | null): Promise<{ stopped: boolean }> {
  return request<{ stopped: boolean }>("/api/remote/session", {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })
}

export function sendRemoteInput(token: string, input: RemoteInput): Promise<{ accepted: boolean }> {
  return request<{ accepted: boolean }>("/api/remote/input", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(input),
  })
}

export function openRemoteAccessibilitySettings(
  token?: string | null,
): Promise<{ opened: boolean; permission_target: string }> {
  return request<{ opened: boolean; permission_target: string }>("/api/remote/permissions/accessibility", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })
}

export function launchRemoteApplication(
  token: string,
  app: RemoteApplication,
): Promise<{ opened: boolean; app: RemoteApplication; application: string }> {
  return request<{ opened: boolean; app: RemoteApplication; application: string }>("/api/remote/app", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ app }),
  })
}

export async function getRemoteFrame(token: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/remote/frame`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`Screen unavailable (${res.status})`)
  return res.blob()
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
