import type { CSSProperties } from "react"

import { AVATAR_STATE_DESCRIPTIONS, AVATAR_STATE_LABELS, type AvatarState } from "@/avatar/stateMachine"
import { cn } from "@/lib/utils"

type SandStyle = CSSProperties & {
  "--sand-x": string
  "--sand-y": string
  "--sand-size": string
  "--sand-alpha": number
  "--sand-delay": string
  "--sand-speed": string
}

const PARTICLES_PER_LAYER = 62
const SWARM_LAYERS = Array.from({ length: 3 }, (_, layer) => (
  Array.from({ length: PARTICLES_PER_LAYER }, (_, index) => {
    const progress = (index + 0.7) / PARTICLES_PER_LAYER
    const angle = index * 2.399963 + layer * 0.78
    const radius = Math.sqrt(progress) * (42 + layer * 14)
    const wave = Math.sin(index * 1.73 + layer) * 5
    const x = Math.cos(angle) * (radius + wave)
    const y = Math.sin(angle) * (radius + wave) * 0.78
    const size = 1.1 + ((index * 7 + layer * 3) % 7) * 0.28
    const alpha = 0.4 + ((index * 11 + layer) % 6) * 0.1
    return {
      id: `${layer}-${index}`,
      tone: (index + layer * 2) % 5,
      style: {
        "--sand-x": `${x.toFixed(2)}px`,
        "--sand-y": `${y.toFixed(2)}px`,
        "--sand-size": `${size.toFixed(2)}px`,
        "--sand-alpha": alpha,
        "--sand-delay": `${(-index * 0.11 - layer * 0.7).toFixed(2)}s`,
        "--sand-speed": `${(2.2 + ((index + layer) % 7) * 0.31).toFixed(2)}s`,
      } as SandStyle,
    }
  })
))

export function GriffinPresence({ state }: { state: AvatarState }) {
  return (
    <div className={cn("griffin-presence", `griffin-presence--${state.toLowerCase()}`)} aria-live="polite">
      <div className="griffin-swarm" aria-hidden>
        {SWARM_LAYERS.map((particles, layer) => (
          <div key={layer} className={cn("griffin-swarm__layer", `griffin-swarm__layer--${layer + 1}`)}>
            {particles.map((particle) => (
              <span
                key={particle.id}
                className={cn("griffin-swarm__grain", `griffin-swarm__grain--${particle.tone}`)}
                style={particle.style}
              />
            ))}
          </div>
        ))}
      </div>
      <p className="griffin-presence__state">{AVATAR_STATE_LABELS[state]}</p>
      <p className="griffin-presence__description">{AVATAR_STATE_DESCRIPTIONS[state]}</p>
    </div>
  )
}
