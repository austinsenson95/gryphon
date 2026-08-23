import { CheckCircle2, Diamond, Loader2, Wrench, XCircle } from "lucide-react"

import {
  GlassCard,
  GlassCardContent,
  GlassCardDescription,
  GlassCardHeader,
  GlassCardTitle,
} from "@/components/ui/glass-card"
import { useGriffinEvents } from "@/lib/useGriffinEvents"

function formatArgs(args?: Record<string, unknown>): string | null {
  if (!args || Object.keys(args).length === 0) return null
  const text = JSON.stringify(args)
  return text.length > 80 ? `${text.slice(0, 77)}…` : text
}

export function ToolActivityCard({ className }: { className?: string }) {
  const { toolActivity } = useGriffinEvents()

  return (
    <GlassCard className={className}>
      <GlassCardHeader>
        <GlassCardTitle>Tool Activity</GlassCardTitle>
        <GlassCardDescription className="text-muted-foreground">
          Recent actions performed by Griffin.
        </GlassCardDescription>
      </GlassCardHeader>
      <GlassCardContent>
        {toolActivity.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-6 text-center">
            <Diamond className="h-5 w-5 text-white/35" aria-hidden />
            <p className="text-sm font-medium text-white/70">
              No tool activity yet
            </p>
            <p className="max-w-[32ch] text-xs leading-relaxed text-white/50">
              Griffin's browser, filesystem, and external tools will appear
              here.
            </p>
          </div>
        ) : (
          <ul
            className="flex max-h-56 flex-col gap-2 overflow-y-auto pr-1"
            aria-label="Tool calls"
          >
            {toolActivity.map((tool) => (
              <li
                key={tool.id}
                className="event-enter flex items-center gap-3 rounded-lg border border-white/8 bg-white/[0.06] px-3 py-2"
              >
                {tool.success === null ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-cyan-300" />
                ) : tool.success ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                ) : (
                  <XCircle className="h-4 w-4 shrink-0 text-red-400" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1.5 truncate text-sm font-medium text-white/90">
                    <Wrench className="h-3 w-3 text-white/50" />
                    {tool.name}
                  </p>
                  {formatArgs(tool.args) && (
                    <p className="truncate font-mono text-[11px] text-white/50">
                      {formatArgs(tool.args)}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </GlassCardContent>
    </GlassCard>
  )
}
