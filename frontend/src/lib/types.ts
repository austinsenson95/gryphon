/** Shared contracts mirrored from SPEC §2 (backend) / §3 (frontend). */

export const EVENT_TYPES = [
  "SESSION_CREATED",
  "MESSAGE_RECEIVED",
  "AGENT_STARTED",
  "AGENT_THINKING",
  "TOOL_CALL_STARTED",
  "TOOL_CALL_COMPLETED",
  "TOOL_CALL_FAILED",
  "AGENT_RESPONSE",
  "TASK_STARTED",
  "TASK_COMPLETED",
  "TASK_FAILED",
  "USER_APPROVAL_REQUIRED",
  "STT_STARTED",
  "STT_COMPLETED",
  "STT_FAILED",
  "WORKFLOW_STARTED",
  "WORKFLOW_COMPLETED",
  "PERMISSION_REQUIRED",
  "PERMISSION_GRANTED",
  "PERMISSION_DENIED",
  "BROWSER_NAVIGATION",
  "BROWSER_PAGE_LOADED",
] as const

export type EventType = (typeof EVENT_TYPES)[number]

/** Exact event envelope emitted by the backend event bus (SPEC §2). */
export interface GryphonEvent {
  id: string
  type: EventType
  timestamp: string
  session_id: string | null
  task_id: string | null
  run_id: string | null
  data: Record<string, unknown>
}

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed"

export type LLMProvider = "ollama" | "xai" | "mock"

export interface HealthResponse {
  status: string
  service: string
  version?: string
  llm_mode?: "live" | "mock"
}

export interface ProviderInfoResponse {
  provider: LLMProvider
  mode: "live" | "mock"
  available: LLMProvider[]
}

export interface VoiceResponse extends ChatResponse {
  transcript: string
}

export interface ChatToolCall {
  id?: string
  name?: string
  tool?: string
  arguments?: Record<string, unknown>
  [key: string]: unknown
}

export interface ChatResponse {
  run_id: string | null
  message_id: string
  task_id: string
  session_id: string
  response: string
  tool_calls: ChatToolCall[]
}

export interface BrowserStatus {
  active: boolean
  mock: boolean
  url: string | null
  title: string | null
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  createdAt: string
}

export interface CurrentTask {
  id: string
  status: "running" | "completed" | "failed"
  input?: string
  result?: string
}

export interface ToolActivityItem {
  id: string
  name: string
  args?: Record<string, unknown>
  success: boolean | null // null = in-flight
  timestamp: string
}

export interface AppNotification {
  id: string
  level: "info" | "warning" | "error"
  title: string
  body: string
}
