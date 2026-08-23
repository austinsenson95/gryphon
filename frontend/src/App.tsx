import {
  AVATAR_STATE_DESCRIPTIONS,
  AVATAR_STATE_LABELS,
} from "@/avatar/stateMachine"
import { AvatarRenderer } from "@/avatar/AvatarRenderer"
import { ActivityTimeline } from "@/activity/ActivityTimeline"
import { ChatPanel } from "@/dashboard/ChatPanel"
import { CurrentTaskCard } from "@/tasks/CurrentTaskCard"
import { ToolActivityCard } from "@/tasks/ToolActivityCard"
import { NotificationStack } from "@/notifications/NotificationStack"
import {
  GlassCard,
  GlassCardContent,
  GlassCardDescription,
  GlassCardHeader,
  GlassCardTitle,
} from "@/components/ui/glass-card"
import { GhibliRobotHero } from "@/components/ui/ghibli-robot-hero"
import { GRYPHON_HERO_BACKGROUND } from "@/components/ui/ghibli-robot-hero.demo"
import { GryphonProvider, useGryphonEvents } from "@/lib/useGryphonEvents"
import { cn } from "@/lib/utils"
import type { ConnectionStatus, LLMProvider } from "@/lib/types"
import { useState } from "react"
import { Laptop, Smartphone } from "lucide-react"
import { RemoteCockpit } from "@/remote/RemoteCockpit"
import { DesktopRemoteCard } from "@/remote/DesktopRemoteCard"

type ViewMode = "desktop" | "phone"

const DOT_STYLES: Record<ConnectionStatus, string> = {
  open: "bg-emerald-400",
  connecting: "bg-amber-400 animate-pulse",
  reconnecting: "bg-amber-400 animate-pulse",
  closed: "bg-red-500",
}

const DOT_LABELS: Record<ConnectionStatus, string> = {
  open: "Connected",
  connecting: "Connecting",
  reconnecting: "Reconnecting",
  closed: "Disconnected",
}

const PROVIDER_LABELS: Record<LLMProvider, string> = {
  ollama: "Ollama",
  xai: "xAI",
  mock: "Mock",
}

function ProviderToggle() {
  const { healthOk, llmMode, provider, availableProviders, switchingProvider, switchProvider } =
    useGryphonEvents()

  return (
    <div className="flex items-center gap-2">
      <span
        data-testid="llm-mode-badge"
        className={cn(
          "rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider backdrop-blur-sm",
          healthOk
            ? llmMode === "live"
              ? "border-emerald-300/35 bg-emerald-400/15 text-emerald-200"
              : "border-amber-300/35 bg-amber-400/15 text-amber-200"
            : "border-red-400/35 bg-red-500/15 text-red-300",
        )}
      >
        {healthOk ? (llmMode === "live" ? "LIVE" : "MOCK") : "Offline"}
      </span>
      <select
        aria-label="LLM provider"
        data-testid="provider-toggle"
        value={provider ?? ""}
        disabled={!healthOk || switchingProvider}
        onChange={(e) => switchProvider(e.target.value as LLMProvider)}
        className={cn(
          "h-7 cursor-pointer rounded-lg border bg-slate-950/40 px-2 text-xs font-medium text-white/90 backdrop-blur-sm transition-opacity focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyan-300/40",
          switchingProvider ? "opacity-60 cursor-wait" : "hover:bg-slate-900/60",
        )}
      >
        <option value="" disabled>
          {switchingProvider ? "Switching…" : "Provider"}
        </option>
        {availableProviders.map((p) => (
          <option key={p} value={p}>
            {PROVIDER_LABELS[p]}
          </option>
        ))}
      </select>
    </div>
  )
}

function Header({ mode, onMode }: { mode: ViewMode; onMode: (mode: ViewMode) => void }) {
  const { connectionStatus } = useGryphonEvents()
  return (
    <header className="flex flex-wrap items-center gap-3">
      <h1 className="bg-gradient-to-r from-amber-300 via-amber-400 to-cyan-300 bg-clip-text text-2xl font-bold tracking-[0.3em] text-transparent">
        GRYPHON
      </h1>
      <span className="flex items-center gap-1.5 text-xs font-medium text-white/75">
        <span
          data-testid="connection-dot"
          className={cn("h-2.5 w-2.5 rounded-full", DOT_STYLES[connectionStatus])}
          style={
            connectionStatus === "open"
              ? { boxShadow: "0 0 8px rgba(52,211,153,0.55)" }
              : undefined
          }
          title={DOT_LABELS[connectionStatus]}
        />
        {DOT_LABELS[connectionStatus]}
      </span>
      <ProviderToggle />
      <div aria-label="Portal mode" className="ml-auto flex rounded-xl border border-white/10 bg-slate-950/45 p-1 backdrop-blur-xl">
        <button aria-pressed={mode === "desktop"} onClick={() => onMode("desktop")} className={cn("flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition", mode === "desktop" ? "bg-amber-300 text-slate-950 shadow-sm" : "text-slate-300 hover:text-white")}><Laptop className="h-3.5 w-3.5" />Desktop</button>
        <button aria-pressed={mode === "phone"} onClick={() => onMode("phone")} className={cn("flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition", mode === "phone" ? "bg-cyan-200 text-slate-950 shadow-sm" : "text-slate-300 hover:text-white")}><Smartphone className="h-3.5 w-3.5" />Phone</button>
      </div>
    </header>
  )
}

function PresenceCard() {
  const { avatarState } = useGryphonEvents()
  return (
    <GlassCard>
      <GlassCardHeader>
        <GlassCardTitle>Gryphon</GlassCardTitle>
        <GlassCardDescription className="text-muted-foreground">
          {AVATAR_STATE_DESCRIPTIONS[avatarState]}
        </GlassCardDescription>
      </GlassCardHeader>
      <GlassCardContent>
        <p className="flex items-center gap-2 text-sm">
          <span className="text-xs uppercase tracking-wide text-muted-foreground">
            Presence
          </span>
          <span
            data-testid="presence-state"
            className="rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-xs font-semibold"
          >
            {AVATAR_STATE_LABELS[avatarState]}
          </span>
        </p>
        <p className="mt-3 text-xs leading-relaxed text-white/60">
          Drag the avatar anywhere on screen. Click it to jump to chat,
          double-click to recenter.
        </p>
      </GlassCardContent>
    </GlassCard>
  )
}

function BackgroundHero() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-0">
      <GhibliRobotHero
        image={GRYPHON_HERO_BACKGROUND}
        focus="62% 58%"
        scrim={0.9}
        title=""
        minHeight="100svh"
      />
      {/* Readability stage: a cool veil pooled behind the dashboard region,
          fading out toward the edges so the artwork stays visible. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 90% at 50% 42%, rgba(8,18,38,0.42) 0%, rgba(8,18,38,0.22) 55%, rgba(8,18,38,0) 88%)",
        }}
      />
    </div>
  )
}

function Dashboard() {
  const { avatarState } = useGryphonEvents()
  const [mode, setMode] = useState<ViewMode>(() => {
    const params = new URLSearchParams(location.search)
    return params.get("mode") === "phone" || params.has("remote") ? "phone" : "desktop"
  })
  const changeMode = (next: ViewMode) => {
    setMode(next)
    const url = new URL(location.href)
    url.searchParams.delete("remote")
    if (next === "phone") url.searchParams.set("mode", "phone")
    else url.searchParams.delete("mode")
    window.history.replaceState({}, "", url)
  }
  return (
    <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 overflow-x-hidden p-4 sm:p-6">
      <Header mode={mode} onMode={changeMode} />
      {mode === "phone" ? <RemoteCockpit /> : <main className="grid w-full grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        <PresenceCard />
        <CurrentTaskCard />
        <ChatPanel />
        <DesktopRemoteCard />
        <ActivityTimeline />
        <ToolActivityCard className="md:col-span-2" />
      </main>}
      {mode === "desktop" && <AvatarRenderer state={avatarState} />}
      <NotificationStack />
    </div>
  )
}

export default function App() {
  return (
    <GryphonProvider>
      <BackgroundHero />
      <Dashboard />
    </GryphonProvider>
  )
}
