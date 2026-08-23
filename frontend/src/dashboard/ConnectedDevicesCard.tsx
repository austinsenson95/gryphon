import { Laptop, Smartphone } from "lucide-react"
import { useEffect, useState } from "react"

import { GlassCard, GlassCardContent, GlassCardHeader, GlassCardTitle } from "@/components/ui/glass-card"
import { getRemoteStatus } from "@/lib/api"
import type { RemoteStatus } from "@/lib/types"

export function ConnectedDevicesCard() {
  const [remote, setRemote] = useState<RemoteStatus | null>(null)

  useEffect(() => {
    let cancelled = false
    const refresh = () => getRemoteStatus().then((status) => { if (!cancelled) setRemote(status) }).catch(() => undefined)
    void refresh()
    const timer = window.setInterval(refresh, 5_000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [])

  const phoneConnected = remote?.state === "paired"
  return (
    <GlassCard className="griffin-devices-card">
      <GlassCardHeader><GlassCardTitle>Connected devices</GlassCardTitle></GlassCardHeader>
      <GlassCardContent>
        <div className="griffin-device-row"><Laptop className="h-4 w-4" aria-hidden /><span>{remote?.device_name ?? "This Mac"}</span><strong className="is-online">Online</strong></div>
        <div className="griffin-device-row"><Smartphone className="h-4 w-4" aria-hidden /><span>Phone remote</span><strong className={phoneConnected ? "is-online" : ""}>{phoneConnected ? "Connected" : "Available"}</strong></div>
      </GlassCardContent>
    </GlassCard>
  )
}
