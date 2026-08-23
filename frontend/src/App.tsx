import { CircleUserRound, Laptop, LayoutDashboard, Moon, Smartphone, SunMedium } from "lucide-react"
import { useState } from "react"

import { NotificationStack } from "@/notifications/NotificationStack"
import { GriffinProvider } from "@/lib/useGriffinEvents"
import { ChatPanel } from "@/dashboard/ChatPanel"
import { RemoteCockpit } from "@/remote/RemoteCockpit"
import { DesktopRemoteCard } from "@/remote/DesktopRemoteCard"
import { CurrentTaskCard } from "@/tasks/CurrentTaskCard"
import { ToolActivityCard } from "@/tasks/ToolActivityCard"
import { ActivityTimeline } from "@/activity/ActivityTimeline"
import { cn } from "@/lib/utils"

type ViewMode = "desktop" | "phone"

function Header({ mode, onMode, theme, onTheme }: { mode: ViewMode; onMode: (mode: ViewMode) => void; theme: "light" | "dark"; onTheme: () => void }) {
  return <header className="griffin-header">
    <div className="griffin-brand"><span className="griffin-brand__icon"><LayoutDashboard className="h-4 w-4" strokeWidth={1.65} /></span><span>Griffin OS</span></div>
    <div className="griffin-header__right">
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
  const [theme, setTheme] = useState<"light" | "dark">(() => window.localStorage.getItem("griffin.theme") === "dark" ? "dark" : "light")
  const toggleTheme = () => setTheme((current) => {
    const next = current === "light" ? "dark" : "light"
    window.localStorage.setItem("griffin.theme", next)
    return next
  })
  return <div className="griffin-app" data-theme={theme}><Header mode={mode} onMode={changeMode} theme={theme} onTheme={toggleTheme} />{mode === "phone" ? <RemoteCockpit /> : <main className="griffin-workspace"><ChatPanel /><aside className="griffin-dashboard" aria-label="Mac controls"><DesktopRemoteCard /><CurrentTaskCard /><ToolActivityCard /><ActivityTimeline /></aside></main>}<NotificationStack /></div>
}

export default function App() { return <GriffinProvider><Dashboard /></GriffinProvider> }
