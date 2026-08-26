import { CircleUserRound, Laptop, LayoutDashboard, MessageCircle, Moon, PhoneOutgoing, Smartphone, SunMedium } from "lucide-react"
import { useState } from "react"

import { NotificationStack } from "@/notifications/NotificationStack"
import { GriffinProvider } from "@/lib/useGriffinEvents"
import { ChatPanel } from "@/dashboard/ChatPanel"
import { RemoteCockpit } from "@/remote/RemoteCockpit"
import { DesktopRemoteCard } from "@/remote/DesktopRemoteCard"
import { CurrentTaskCard } from "@/tasks/CurrentTaskCard"
import { ToolActivityCard } from "@/tasks/ToolActivityCard"
import { ActivityTimeline } from "@/activity/ActivityTimeline"
import { ConnectedDevicesCard } from "@/dashboard/ConnectedDevicesCard"
import { SystemStatusCard } from "@/dashboard/SystemStatusCard"
import { cn } from "@/lib/utils"
import { PhoneCallDashboard } from "@/phone/PhoneCallDashboard"

type ViewMode = "desktop" | "phone"
type WorkspaceView = "assistant" | "calls"

function Header({ mode, onMode, view, onView, theme, onTheme }: { mode: ViewMode; onMode: (mode: ViewMode) => void; view: WorkspaceView; onView: (view: WorkspaceView) => void; theme: "light" | "dark"; onTheme: () => void }) {
  return <header className="griffin-header">
    <div className="griffin-brand"><span className="griffin-brand__icon"><LayoutDashboard className="h-4 w-4" strokeWidth={1.65} /></span><span>Griffin OS</span></div>
    <div className="griffin-header__right">
      <nav className="griffin-section-switch" aria-label="Workspace">
        <button data-testid="assistant-nav" aria-pressed={view === "assistant"} onClick={() => onView("assistant")} className={cn(view === "assistant" && "is-active")}><MessageCircle /><span>Assistant</span></button>
        <button data-testid="calls-nav" aria-pressed={view === "calls"} onClick={() => onView("calls")} className={cn(view === "calls" && "is-active")}><PhoneOutgoing /><span>Calls</span></button>
      </nav>
      <div aria-label="View mode" className="griffin-view-switch">
        <button aria-label="Desktop view" aria-pressed={mode === "desktop"} onClick={() => onMode("desktop")} className={cn(mode === "desktop" && "is-active")}><Laptop className="h-4 w-4" /></button>
        <button aria-label="Phone" aria-pressed={mode === "phone"} onClick={() => onMode("phone")} className={cn(mode === "phone" && "is-active")}><Smartphone className="h-4 w-4" /></button>
      </div>
      <button className="griffin-icon-button" aria-label="Griffin account" type="button"><CircleUserRound aria-hidden className="h-5 w-5" strokeWidth={1.65} /></button>
      <button className="griffin-icon-button" aria-label="Toggle dark mode" aria-pressed={theme === "dark"} onClick={onTheme} type="button">{theme === "dark" ? <SunMedium aria-hidden className="h-5 w-5" strokeWidth={1.65} /> : <Moon aria-hidden className="h-5 w-5" strokeWidth={1.65} />}</button>
    </div>
  </header>
}

function Dashboard() {
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
  const [view, setView] = useState<WorkspaceView>(() => new URLSearchParams(location.search).get("view") === "calls" ? "calls" : "assistant")
  const changeView = (next: WorkspaceView) => {
    setView(next)
    const url = new URL(location.href)
    if (next === "calls") url.searchParams.set("view", "calls")
    else url.searchParams.delete("view")
    window.history.replaceState({}, "", url)
  }
  const [theme, setTheme] = useState<"light" | "dark">(() => window.localStorage.getItem("griffin.theme") === "light" ? "light" : "dark")
  const toggleTheme = () => setTheme((current) => {
    const next = current === "light" ? "dark" : "light"
    window.localStorage.setItem("griffin.theme", next)
    return next
  })
  return <div className="griffin-app" data-mode={mode} data-theme={theme}><Header mode={mode} onMode={changeMode} view={view} onView={changeView} theme={theme} onTheme={toggleTheme} />{view === "calls" ? <PhoneCallDashboard /> : mode === "phone" ? <RemoteCockpit /> : <main className="griffin-workspace"><ChatPanel /><aside className="griffin-dashboard" aria-label="Mac controls"><SystemStatusCard /><CurrentTaskCard /><ToolActivityCard /><ActivityTimeline /><ConnectedDevicesCard /><DesktopRemoteCard /></aside></main>}<NotificationStack /></div>
}

export default function App() { return <GriffinProvider><Dashboard /></GriffinProvider> }
