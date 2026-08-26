import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react"

import { cn } from "@/lib/utils"

export function MetalPanel({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("hw-metal-panel", className)} {...props}>{children}</div>
}

export function RecessedPanel({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("hw-recessed-panel", className)} {...props}>{children}</div>
}

export function WoodPanel({ className, children, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={cn("hw-wood-panel", className)} {...props}>{children}</section>
}

export function EngravedLabel({ className, children, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("hw-engraved-label", className)} {...props}>{children}</span>
}

export function InstrumentDisplay({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("hw-instrument-display", className)} {...props}>{children}</div>
}

type PhysicalButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: "dark" | "metal" | "amber"
}

export function PhysicalButton({ className, children, tone = "dark", type = "button", ...props }: PhysicalButtonProps) {
  return <button type={type} className={cn("hw-physical-button", `hw-physical-button--${tone}`, className)} {...props}>{children}</button>
}

export function StatusLED({ state = "off", label }: { state?: "off" | "green" | "amber" | "red" | "cyan"; label: string }) {
  return <span className="hw-status-led"><span aria-hidden className={cn("hw-status-led__lamp", `is-${state}`)} /><span>{label}</span></span>
}

export function ControlGroup({ label, meta, children, className }: { label: string; meta?: ReactNode; children: ReactNode; className?: string }) {
  return <MetalPanel className={className}>
    <div className="hw-control-heading"><EngravedLabel>{label}</EngravedLabel>{meta}</div>
    {children}
  </MetalPanel>
}
