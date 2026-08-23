import { CircleUserRound, Laptop, Smartphone, SunMedium } from "lucide-react"
import { useState } from "react"

import { NotificationStack } from "@/notifications/NotificationStack"
import { GriffinProvider } from "@/lib/useGriffinEvents"
import { ChatPanel } from "@/dashboard/ChatPanel"
import { RemoteCockpit } from "@/remote/RemoteCockpit"
import { cn } from "@/lib/utils"

type ViewMode = "desktop" | "phone"

function Header({ mode, onMode }: { mode: ViewMode; onMode: (mode: ViewMode) => void }) {
  return <header className="griffin-header">
    <button className="griffin-icon-button" aria-label="Griffin account" type="button"><CircleUserRound aria-hidden className="h-5 w-5" strokeWidth={1.65} /></button>
    <div className="griffin-header__right">
      <div aria-label="View mode" className="griffin-view-switch">
        <button aria-label="Desktop view" aria-pressed={mode === "desktop"} onClick={() => onMode("desktop")} className={cn(mode === "desktop" && "is-active")}><Laptop className="h-4 w-4" /></button>
        <button aria-label="Phone" aria-pressed={mode === "phone"} onClick={() => onMode("phone")} className={cn(mode === "phone" && "is-active")}><Smartphone className="h-4 w-4" /></button>
      </div>
      <button className="griffin-icon-button" aria-label="Appearance" type="button"><SunMedium aria-hidden className="h-5 w-5" strokeWidth={1.65} /></button>
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
  return <div className="griffin-app"><Header mode={mode} onMode={changeMode} />{mode === "phone" ? <RemoteCockpit /> : <ChatPanel />}<NotificationStack /></div>
}

export default function App() { return <GriffinProvider><Dashboard /></GriffinProvider> }
