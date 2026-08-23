import { fireEvent, render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { AvatarRenderer } from "@/avatar/AvatarRenderer"
import type { AvatarState } from "@/avatar/stateMachine"

const STATES: AvatarState[] = [
  "IDLE",
  "LISTENING",
  "THINKING",
  "WORKING",
  "SUCCESS",
  "ERROR",
  "WAITING",
]

describe("AvatarRenderer", () => {
  it("changes its state class per avatar state", () => {
    const { rerender, getByRole } = render(<AvatarRenderer state="IDLE" />)
    for (const state of STATES) {
      rerender(<AvatarRenderer state={state} />)
      const el = getByRole("button", { name: /griffin avatar/i })
      expect(el.className).toContain(`avatar--${state.toLowerCase()}`)
    }
  })

  it("references /avatar/griffin.png and falls back gracefully on error", () => {
    const { container, getByRole, getByTestId } = render(
      <AvatarRenderer state="IDLE" />,
    )
    const img = container.querySelector("img")
    expect(img).toHaveAttribute("src", "/avatar/idle/griffin.png")

    fireEvent.error(img!)
    expect(getByTestId("avatar-fallback")).toBeInTheDocument()
    expect(getByRole("button", { name: /griffin avatar/i })).toBeInTheDocument()
  })
})
