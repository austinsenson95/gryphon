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
  "REMOTE_SESSION_STARTED",
  "REMOTE_DEVICE_PAIRED",
  "REMOTE_SESSION_STOPPED",
  "PHONE_CALL_QUEUED",
  "PHONE_CALL_STARTED",
  "PHONE_CALL_ANSWERED",
  "PHONE_CALL_TRANSCRIPT",
  "PHONE_CALL_COMPLETED",
  "PHONE_CALL_FAILED",
  "WHATSAPP_ACTION_UPDATED",
] as const

export type EventType = (typeof EVENT_TYPES)[number]

/** Exact event envelope emitted by the backend event bus (SPEC §2). */
export interface GriffinEvent {
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
  phone_mode?: "live" | "mock"
}

export interface PhoneContact {
  id: string
  name: string
  phone_number: string
  notes: string
  created_at: string
}

export interface PhoneTurn {
  speaker: "user" | "assistant"
  text: string
  timestamp: string
}

export interface PhoneQuestion {
  id: string
  question: string
  required: boolean
}

export interface PhoneFinding {
  question: string
  answer: string
}

export interface PhoneCall {
  id: string
  contact_id: string | null
  contact_name: string
  phone_number: string
  mission: string
  questions: PhoneQuestion[]
  status: "queued" | "ringing" | "active" | "completed" | "declined" | "incomplete" | "failed" | "cancelled"
  provider_call_id: string | null
  session_id: string | null
  task_id: string | null
  transcript: PhoneTurn[]
  findings: Record<string, PhoneFinding>
  summary: string | null
  error: string | null
  duration_seconds: number | null
  created_at: string
  started_at: string | null
  answered_at: string | null
  ended_at: string | null
  updated_at: string
  mock?: boolean
}

export interface PhoneStatus {
  mode: "live" | "mock"
  number_configured: boolean
  public_url_configured: boolean
  speech_to_text_configured: boolean
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

export interface RemoteStatus {
  supported: boolean
  device_name: string
  lan_address: string | null
  state: "idle" | "pairing" | "paired"
  expires_at: string | null
  permissions: {
    screen_recording: boolean
    accessibility: boolean
  }
  permission_target?: string | null
  ready: boolean
  can_start?: boolean
  pairing_code?: string
}

export interface RemotePairResponse extends RemoteStatus {
  token: string
}

export type RemoteInput =
  | { type: "tap" | "double_tap" | "secondary_tap" | "move"; x: number; y: number }
  | { type: "scroll"; dx?: number; dy: number }
  | { type: "move_window"; dx: number; dy: number }
  | { type: "select_window" | "release_window" }
  | { type: "text"; text: string }
  | { type: "key"; key: string; modifiers?: string[] }
  | { type: "volume"; volume: number }
  | { type: "enter_fullscreen" | "exit_fullscreen" }

export type RemoteApplication = string

export interface RemoteApplicationOption {
  id: string
  name: string
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

export type WhatsAppActionStatus = "approval_required" | "approved" | "executing" | "sent" | "failed" | "uncertain" | "cancelled" | "expired"

export interface WhatsAppAction {
  action_id: string
  recipient: string
  message: string
  message_hash: string
  status: WhatsAppActionStatus
  expires_at: string
  created_at: string
  sent_at?: string | null
}
