import { fireEvent, render } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  AVATAR_ACTIVATE_EVENT,
  AVATAR_POSITION_KEY,
  AvatarRenderer,
} from "@/avatar/AvatarRenderer"

describe("AvatarRenderer dragging", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("drags via pointer events, updates position and persists to localStorage", () => {
    const { getByRole } = render(<AvatarRenderer state="IDLE" size={96} />)
    const el = getByRole("button", { name: /griffin avatar/i })

    const startLeft = parseFloat(el.style.left)
    const startTop = parseFloat(el.style.top)

    fireEvent.pointerDown(el, { pointerId: 1, clientX: 900, clientY: 500 })
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 800, clientY: 400 })
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 800, clientY: 400 })

    expect(parseFloat(el.style.left)).toBe(startLeft - 100)
    expect(parseFloat(el.style.top)).toBe(startTop - 100)

    const stored = window.localStorage.getItem(AVATAR_POSITION_KEY)
    expect(stored).not.toBeNull()
    expect(JSON.parse(stored!)).toEqual({
      x: startLeft - 100,
      y: startTop - 100,
    })
  })

  it("treats a sub-threshold press as a click, not a drag", () => {
    const onActivate = vi.fn()
    window.addEventListener(AVATAR_ACTIVATE_EVENT, onActivate)
    const { getByRole } = render(<AvatarRenderer state="IDLE" size={96} />)
    const el = getByRole("button", { name: /griffin avatar/i })
    const startLeft = el.style.left

    fireEvent.pointerDown(el, { pointerId: 1, clientX: 900, clientY: 500 })
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 901, clientY: 500 })
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 901, clientY: 500 })

    expect(onActivate).toHaveBeenCalledTimes(1)
    expect(window.localStorage.getItem(AVATAR_POSITION_KEY)).toBeNull()
    expect(el.style.left).toBe(startLeft)
    window.removeEventListener(AVATAR_ACTIVATE_EVENT, onActivate)
  })

  it("clamps the position to the viewport", () => {
    const { getByRole } = render(<AvatarRenderer state="IDLE" size={96} />)
    const el = getByRole("button", { name: /griffin avatar/i })

    fireEvent.pointerDown(el, { pointerId: 1, clientX: 500, clientY: 500 })
    fireEvent.pointerMove(el, { pointerId: 1, clientX: -5000, clientY: -5000 })
    fireEvent.pointerUp(el, { pointerId: 1, clientX: -5000, clientY: -5000 })

    expect(parseFloat(el.style.left)).toBeGreaterThanOrEqual(0)
    expect(parseFloat(el.style.top)).toBeGreaterThanOrEqual(0)
    const stored = JSON.parse(window.localStorage.getItem(AVATAR_POSITION_KEY)!)
    expect(stored.x).toBeGreaterThanOrEqual(0)
    expect(stored.y).toBeGreaterThanOrEqual(0)
  })

  it("double-click recenters and clears the persisted position", () => {
    window.localStorage.setItem(
      AVATAR_POSITION_KEY,
      JSON.stringify({ x: 10, y: 10 }),
    )
    const { getByRole } = render(<AvatarRenderer state="IDLE" size={96} />)
    const el = getByRole("button", { name: /griffin avatar/i })
    expect(parseFloat(el.style.left)).toBe(12) // clamped by viewport margin

    fireEvent.doubleClick(el)

    expect(window.localStorage.getItem(AVATAR_POSITION_KEY)).toBeNull()
    expect(parseFloat(el.style.left)).toBeGreaterThan(12)
  })
})
