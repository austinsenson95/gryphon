import { CheckCircle2, Loader2, XCircle } from "lucide-react"

import {
  GlassCard,
  GlassCardContent,
  GlassCardDescription,
  GlassCardHeader,
  GlassCardTitle,
} from "@/components/ui/glass-card"
import { useGryphonEvents } from "@/lib/useGryphonEvents"
import { cn } from "@/lib/utils"

const STATUS_STYLES: Record<string, string> = {
  running: "bg-cyan-400/15 text-cyan-200 border-cyan-300/35",
  completed: "bg-emerald-400/15 text-emerald-200 border-emerald-300/35",
  failed: "bg-red-500/15 text-red-300 border-red-400/35",
  waiting: "bg-white/10 text-white/75 border-white/20",
}

export function CurrentTaskCard() {
  const { currentTask } = useGryphonEvents()

  return (
    <GlassCard>
      <GlassCardHeader>
        <GlassCardTitle>Current Task</GlassCardTitle>
        <GlassCardDescription className="text-muted-foreground">
          What Gryphon is currently doing.
        </GlassCardDescription>
      </GlassCardHeader>
      <GlassCardContent>
        {!currentTask ? (
          <p className="text-sm text-white/65">
            No active task. Gryphon is standing by.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2">
              {currentTask.status === "running" ? (
                <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
              ) : currentTask.status === "completed" ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              ) : (
                <XCircle className="h-4 w-4 text-red-400" />
              )}
              <span
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider",
                  STATUS_STYLES[currentTask.status] ?? STATUS_STYLES.waiting,
                )}
              >
                {currentTask.status}
              </span>
              {/* Task ID is metadata — deliberately de-emphasized. */}
              <span className="truncate font-mono text-[11px] text-white/40">
                {currentTask.id}
              </span>
            </div>
            {currentTask.input && (
              <div>
                <p className="text-[11px] font-medium uppercase tracking-wider text-white/55">
                  Input
                </p>
                <p className="mt-1 break-words text-[15px] font-medium text-white/90">
                  {currentTask.input}
                </p>
              </div>
            )}
            {currentTask.result && (
              <div className="rounded-xl border border-white/8 bg-white/[0.04] p-3">
                <p className="text-[11px] font-medium uppercase tracking-wider text-white/55">
                  Result
                </p>
                <p className="mt-1 break-words text-sm leading-relaxed text-white/85">
                  {currentTask.result}
                </p>
              </div>
            )}
          </div>
        )}
      </GlassCardContent>
    </GlassCard>
  )
}
