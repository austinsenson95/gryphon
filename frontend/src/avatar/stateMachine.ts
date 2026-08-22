import type { EventType } from "@/lib/types"

export type AvatarState =
  | "IDLE"
  | "LISTENING"
  | "THINKING"
  | "WORKING"
  | "SUCCESS"
  | "ERROR"
  | "WAITING"

/** Time before SUCCESS / ERROR decay back to IDLE (SPEC §3). */
export const SUCCESS_IDLE_MS = 2_500
export const ERROR_IDLE_MS = 3_000

const EVENT_TO_STATE: Partial<Record<EventType, AvatarState>> = {
  MESSAGE_RECEIVED: "LISTENING",
  AGENT_STARTED: "THINKING",
  AGENT_THINKING: "THINKING",
  TOOL_CALL_STARTED: "WORKING",
  AGENT_RESPONSE: "SUCCESS",
  TASK_COMPLETED: "SUCCESS",
  TOOL_CALL_FAILED: "ERROR",
  TASK_FAILED: "ERROR",
  USER_APPROVAL_REQUIRED: "WAITING",
}

/**
 * Map a backend event onto the avatar state machine (SPEC §3).
 * Returns null when the event does not change the avatar state.
 */
export function nextAvatarState(event: { type: EventType }): AvatarState | null {
  return EVENT_TO_STATE[event.type] ?? null
}

export const AVATAR_STATE_LABELS: Record<AvatarState, string> = {
  IDLE: "Idle",
  LISTENING: "Listening",
  THINKING: "Thinking",
  WORKING: "Working",
  SUCCESS: "Done",
  ERROR: "Error",
  WAITING: "Waiting for approval",
}

export const AVATAR_STATE_DESCRIPTIONS: Record<AvatarState, string> = {
  IDLE: "Ready for your next instruction.",
  LISTENING: "Received your message.",
  THINKING: "Reasoning about the next step.",
  WORKING: "Running tools on your behalf.",
  SUCCESS: "Task completed successfully.",
  ERROR: "Something went wrong.",
  WAITING: "An action needs your approval.",
}
