import { describe, expect, it } from "vitest"

import { parseEvent } from "@/lib/ws"

const VALID_ENVELOPE = {
  id: "evt_01",
  type: "TOOL_CALL_STARTED",
  timestamp: "2025-01-01T00:00:00Z",
  session_id: "sess_1",
  task_id: "task_1",
  run_id: null,
  data: { tool: "system.get_time", input: {} },
}

describe("parseEvent (WS event envelope)", () => {
  it("parses a valid JSON envelope frame", () => {
    const event = parseEvent(JSON.stringify(VALID_ENVELOPE))
    expect(event).toEqual(VALID_ENVELOPE)
  })

  it("accepts already-parsed objects", () => {
    expect(parseEvent(VALID_ENVELOPE)).toEqual(VALID_ENVELOPE)
  })

  it("ignores the CONNECTED hello frame", () => {
    expect(parseEvent(JSON.stringify({ type: "CONNECTED" }))).toBeNull()
  })

  it("rejects malformed JSON", () => {
    expect(parseEvent("not json {")).toBeNull()
  })

  it("rejects envelopes with missing fields or unknown types", () => {
    expect(parseEvent({ ...VALID_ENVELOPE, id: 42 })).toBeNull()
    expect(parseEvent({ ...VALID_ENVELOPE, type: "NOPE" })).toBeNull()
    expect(parseEvent({ type: "TASK_STARTED" })).toBeNull()
    expect(parseEvent(null)).toBeNull()
    expect(parseEvent([1, 2, 3])).toBeNull()
  })

  it("normalizes nullable ids and non-object data", () => {
    const event = parseEvent({
      ...VALID_ENVELOPE,
      session_id: null,
      task_id: null,
      data: null,
    })
    expect(event).toMatchObject({ session_id: null, task_id: null, data: {} })
  })
})
