import {
  AlertTriangle,
  AudioLines,
  Bot,
  Brain,
  CheckCircle2,
  Globe,
  ListTodo,
  MessageSquare,
  MonitorSmartphone,
  PhoneOutgoing,
  Radio,
  Captions,
  Play,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Sparkles,
  Workflow,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react"

import {
  GlassCard,
  GlassCardContent,
  GlassCardDescription,
  GlassCardHeader,
  GlassCardTitle,
} from "@/components/ui/glass-card"
import { useGriffinEvents } from "@/lib/useGriffinEvents"
import type { EventType } from "@/lib/types"

const EVENT_ICONS: Record<EventType, LucideIcon> = {
  SESSION_CREATED: Sparkles,
  MESSAGE_RECEIVED: MessageSquare,
  AGENT_STARTED: Play,
  AGENT_THINKING: Brain,
  TOOL_CALL_STARTED: Wrench,
  TOOL_CALL_COMPLETED: CheckCircle2,
  TOOL_CALL_FAILED: XCircle,
  AGENT_RESPONSE: Bot,
  TASK_STARTED: ListTodo,
  TASK_COMPLETED: CheckCircle2,
  TASK_FAILED: AlertTriangle,
  USER_APPROVAL_REQUIRED: ShieldAlert,
  STT_STARTED: AudioLines,
  STT_COMPLETED: AudioLines,
  STT_FAILED: XCircle,
  WORKFLOW_STARTED: Workflow,
  WORKFLOW_COMPLETED: CheckCircle2,
  PERMISSION_REQUIRED: ShieldAlert,
  PERMISSION_GRANTED: ShieldCheck,
  PERMISSION_DENIED: ShieldX,
  BROWSER_NAVIGATION: Globe,
  BROWSER_PAGE_LOADED: Globe,
  REMOTE_SESSION_STARTED: MonitorSmartphone,
  REMOTE_DEVICE_PAIRED: ShieldCheck,
  REMOTE_SESSION_STOPPED: XCircle,
  PHONE_CALL_QUEUED: PhoneOutgoing,
  PHONE_CALL_STARTED: PhoneOutgoing,
  PHONE_CALL_ANSWERED: Radio,
  PHONE_CALL_TRANSCRIPT: Captions,
  PHONE_CALL_COMPLETED: CheckCircle2,
  PHONE_CALL_FAILED: XCircle,
}

function iconTone(type: EventType): string {
  switch (type) {
    case "TOOL_CALL_FAILED":
    case "TASK_FAILED":
    case "PERMISSION_DENIED":
    case "PHONE_CALL_FAILED":
      return "text-red-400"
    case "USER_APPROVAL_REQUIRED":
    case "PERMISSION_REQUIRED":
    case "PHONE_CALL_QUEUED":
      return "text-amber-400"
    case "TASK_COMPLETED":
    case "TOOL_CALL_COMPLETED":
    case "PERMISSION_GRANTED":
    case "PHONE_CALL_COMPLETED":
      return "text-emerald-400"
    case "AGENT_THINKING":
    case "TOOL_CALL_STARTED":
    case "BROWSER_NAVIGATION":
    case "BROWSER_PAGE_LOADED":
    case "REMOTE_SESSION_STARTED":
    case "REMOTE_DEVICE_PAIRED":
    case "PHONE_CALL_STARTED":
    case "PHONE_CALL_ANSWERED":
    case "PHONE_CALL_TRANSCRIPT":
      return "text-cyan-300"
    default:
      return "text-slate-300"
  }
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleTimeString()
}

export function ActivityTimeline() {
  const { events } = useGriffinEvents()

  return (
    <GlassCard className="min-h-0">
      <GlassCardHeader>
        <GlassCardTitle>Activity Timeline</GlassCardTitle>
        <GlassCardDescription className="text-muted-foreground">
          Live event feed from the Griffin event bus.
        </GlassCardDescription>
      </GlassCardHeader>
      <GlassCardContent>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No events yet. Send Griffin a message to get started.
          </p>
        ) : (
          <ul
            className="flex max-h-72 flex-col gap-2 overflow-y-auto pr-1"
            aria-label="Activity events"
          >
            {events.map((event) => {
              const Icon = EVENT_ICONS[event.type] ?? Sparkles
              return (
                <li
                  key={event.id}
                  className="event-enter flex items-center gap-3 rounded-lg border border-white/8 bg-white/[0.06] px-3 py-2"
                >
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-white/10 bg-white/[0.06]">
                    <Icon className={`h-3.5 w-3.5 ${iconTone(event.type)}`} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-white/90">
                      {event.type.replace(/_/g, " ")}
                    </p>
                    {typeof event.data.message === "string" && (
                      <p className="truncate text-xs text-white/60">
                        {event.data.message}
                      </p>
                    )}
                  </div>
                  <time className="shrink-0 text-[11px] tabular-nums text-white/55">
                    {formatTime(event.timestamp)}
                  </time>
                </li>
              )
            })}
          </ul>
        )}
      </GlassCardContent>
    </GlassCard>
  )
}
