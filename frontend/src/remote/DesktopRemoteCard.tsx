import { useEffect, useMemo, useState } from "react"
import { Check, Copy, Link2, MonitorSmartphone, Power, RefreshCw, ShieldCheck } from "lucide-react"
import { QRCodeSVG } from "qrcode.react"

import { Button } from "@/components/ui/button"
import {
  GlassCard,
  GlassCardContent,
  GlassCardDescription,
  GlassCardHeader,
  GlassCardTitle,
} from "@/components/ui/glass-card"
import { getRemoteStatus, startRemoteSession, stopRemoteSession } from "@/lib/api"
import type { RemoteStatus } from "@/lib/types"

export function DesktopRemoteCard() {
  const [status, setStatus] = useState<RemoteStatus | null>(null)
  const [pairingCode, setPairingCode] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    const refresh = () => getRemoteStatus().then((next) => {
      if (!cancelled) setStatus(next)
    }).catch(() => undefined)
    void refresh()
    const timer = window.setInterval(refresh, 2000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [])

  const phoneUrl = useMemo(() => {
    const host = status?.lan_address ?? location.hostname
    const port = location.port || "5173"
    const url = new URL(`${location.protocol}//${host}:${port}/`)
    url.searchParams.set("mode", "phone")
    if (pairingCode) url.searchParams.set("pair", pairingCode)
    return url.toString()
  }, [pairingCode, status?.lan_address])

  const start = async () => {
    setBusy(true)
    setError("")
    try {
      const next = await startRemoteSession()
      setStatus(next)
      setPairingCode(next.pairing_code ?? null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the phone remote.")
    } finally {
      setBusy(false)
    }
  }

  const stop = async () => {
    setBusy(true)
    try {
      await stopRemoteSession()
      setPairingCode(null)
      setStatus((current) => current ? { ...current, state: "idle", expires_at: null } : current)
    } finally {
      setBusy(false)
    }
  }

  const copyLink = async () => {
    await navigator.clipboard.writeText(phoneUrl)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  return (
    <GlassCard className="remote-stage md:col-span-2 xl:col-span-1">
      <GlassCardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <GlassCardTitle className="flex items-center gap-2"><MonitorSmartphone className="griffin-accent-icon h-5 w-5" />Phone remote</GlassCardTitle>
            <GlassCardDescription className="mt-1 text-muted-foreground">Generate a private code for your phone.</GlassCardDescription>
          </div>
          <span className="rounded-full border border-white/10 bg-white/[.05] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[.16em] text-slate-300">
            {status?.state ?? "checking"}
          </span>
        </div>
      </GlassCardHeader>
      <GlassCardContent>
        {pairingCode && status?.state !== "paired" ? (
          <div className="griffin-qr-pairing rounded-2xl p-4">
            <div className="flex items-start gap-4">
              <div className="shrink-0 rounded-xl bg-white p-2 shadow-sm"><QRCodeSVG value={phoneUrl} size={112} level="M" includeMargin aria-label="Scan to pair this phone" /></div>
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[.2em]">Scan to pair</p>
                <p className="mt-1 text-xs leading-5">Open your phone camera and scan this code. Griffin will open and connect using this session&apos;s passkey.</p>
                <p data-testid="desktop-pairing-code" className="mt-3 font-mono text-3xl font-semibold tracking-[.15em]">{pairingCode}</p>
              </div>
            </div>
            <div className="mt-4 flex items-center gap-2">
              <p className="min-w-0 flex-1 truncate font-mono text-[11px]">{phoneUrl}</p>
              <Button variant="outline" size="icon" aria-label="Copy phone link" onClick={copyLink}>{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}</Button>
            </div>
          </div>
        ) : status?.state === "paired" ? (
          <div className="rounded-2xl border border-emerald-300/20 bg-emerald-400/[.07] p-4">
            <p className="flex items-center gap-2 text-sm font-semibold text-emerald-100"><ShieldCheck className="h-4 w-4" />Phone connected</p>
            <p className="mt-1 text-xs leading-5 text-slate-300">Your phone can now see and control this Mac.</p>
          </div>
        ) : (
          <div className="rounded-2xl border border-white/10 bg-white/[.04] p-4">
            <p className="text-sm leading-6 text-slate-300">Keep Griffin open on this Mac. Start a session, then switch Griffin to Phone mode on your phone.</p>
            <p className="mt-2 flex items-center gap-2 font-mono text-[11px] text-cyan-100/65"><Link2 className="h-3.5 w-3.5" />{phoneUrl}</p>
          </div>
        )}

        {!status?.ready && status?.supported && <p className="mt-3 text-xs leading-5 text-amber-100/80">Before connecting, allow Screen Recording and Accessibility for the app running Griffin in System Settings → Privacy &amp; Security.</p>}
        {error && <p role="alert" className="mt-3 text-xs text-red-300">{error}</p>}

        <Button className="mt-4 w-full" disabled={busy || status?.supported === false} onClick={status?.state === "idle" || !status ? start : stop}>
          {busy ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <Power className="mr-2 h-4 w-4" />}
          {status?.state === "idle" || !status ? "Start phone remote" : "Stop phone remote"}
        </Button>
        {status?.state === "pairing" && !pairingCode && <Button variant="ghost" className="mt-2 w-full text-xs" onClick={start}>Generate a new code</Button>}
      </GlassCardContent>
    </GlassCard>
  )
}
