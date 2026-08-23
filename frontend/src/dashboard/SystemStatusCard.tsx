import { Activity, Cpu, RotateCw, ShieldCheck, Wrench } from "lucide-react"

import { GlassCard, GlassCardContent, GlassCardHeader, GlassCardTitle } from "@/components/ui/glass-card"
import { useGriffinEvents } from "@/lib/useGriffinEvents"

export function SystemStatusCard() {
  const {
    connectionStatus,
    healthOk,
    llmMode,
    provider,
    toolActivity,
    desktopRuntime,
    restartKernel,
  } = useGriffinEvents()
  const online = healthOk && connectionStatus === "open"
  const kernelValue = desktopRuntime?.state ?? (online ? "ready" : connectionStatus)
  const stats = [
    { label: "Model", value: provider ?? llmMode ?? "Checking", icon: Cpu },
    { label: "Kernel", value: kernelValue, icon: Activity },
    { label: "Tools", value: `${toolActivity.length} recent`, icon: Wrench },
    { label: "Privacy", value: "Local", icon: ShieldCheck },
  ]

  return (
    <GlassCard className="griffin-system-status">
      <GlassCardHeader>
        <div className="flex items-center justify-between gap-3">
          <GlassCardTitle>System status</GlassCardTitle>
          <div className="flex items-center gap-2">
            {desktopRuntime && desktopRuntime.state !== "ready" && (
              <button
                type="button"
                className="griffin-kernel-restart"
                onClick={() => void restartKernel()}
                aria-label="Restart Griffin Kernel"
              >
                <RotateCw aria-hidden />
              </button>
            )}
            <span className={online && desktopRuntime?.state !== "failed" ? "griffin-status-dot is-online" : "griffin-status-dot"} aria-label={online ? "System online" : "System connecting"} />
          </div>
        </div>
      </GlassCardHeader>
      <GlassCardContent>
        <div className="grid grid-cols-2 gap-2">
          {stats.map(({ label, value, icon: Icon }) => (
            <div key={label} className="griffin-status-stat">
              <Icon className="h-3.5 w-3.5" aria-hidden />
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
        {desktopRuntime && desktopRuntime.state !== "ready" && (
          <p className="mt-2 text-xs text-slate-500" role="status">
            {desktopRuntime.detail}
          </p>
        )}
      </GlassCardContent>
    </GlassCard>
  )
}
