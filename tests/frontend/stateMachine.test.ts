import { describe, expect, it } from "vitest"

import { nextAvatarState } from "@/avatar/stateMachine"

describe("avatar state machine (SPEC §3 mapping)", () => {
  it.each([
    ["MESSAGE_RECEIVED", "LISTENING"],
    ["AGENT_STARTED", "THINKING"],
    ["AGENT_THINKING", "THINKING"],
    ["TOOL_CALL_STARTED", "WORKING"],
    ["AGENT_RESPONSE", "SUCCESS"],
    ["TASK_COMPLETED", "SUCCESS"],
    ["TOOL_CALL_FAILED", "ERROR"],
    ["TASK_FAILED", "ERROR"],
    ["USER_APPROVAL_REQUIRED", "WAITING"],
  ] as const)("%s -> %s", (type, expected) => {
    expect(nextAvatarState({ type })).toBe(expected)
  })

  it.each(["SESSION_CREATED", "TASK_STARTED"] as const)(
    "%s does not change the avatar state",
    (type) => {
      expect(nextAvatarState({ type })).toBeNull()
    },
  )
})
