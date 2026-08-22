import { AlertTriangle, Info, ShieldAlert, X } from "lucide-react"

import { useGryphonEvents } from "@/lib/useGryphonEvents"
import { cn } from "@/lib/utils"

const LEVEL_STYLES = {
  info: "border-cyan-400/40",
  warning: "border-amber-400/50",
  error: "border-red-400/50",
} as const

const LEVEL_ICONS = {
  info: Info,
  warning: ShieldAlert,
  error: AlertTriangle,
} as const

const LEVEL_ICON_TONES = {
  info: "text-cyan-300",
  warning: "text-amber-300",
  error: "text-red-400",
} as const

export function NotificationStack() {
  const { notifications, dismissNotification } = useGryphonEvents()

  if (notifications.length === 0) return null

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-4 top-4 z-50 flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2"
    >
      {notifications.map((notification) => {
        const Icon = LEVEL_ICONS[notification.level]
        return (
          <div
            key={notification.id}
            role="alert"
            className={cn(
              "pointer-events-auto flex items-start gap-3 rounded-xl border bg-slate-900/90 p-3 shadow-lg backdrop-blur-md",
              LEVEL_STYLES[notification.level],
            )}
          >
            <Icon
              className={cn("mt-0.5 h-4 w-4 shrink-0", LEVEL_ICON_TONES[notification.level])}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{notification.title}</p>
              <p className="break-words text-xs text-muted-foreground">
                {notification.body}
              </p>
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              className="text-muted-foreground transition-colors hover:text-white"
              onClick={() => dismissNotification(notification.id)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
