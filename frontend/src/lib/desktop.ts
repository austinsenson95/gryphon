import type { UnlistenFn } from "@tauri-apps/api/event"

export type DesktopRuntimePhase =
  | "starting"
  | "ready"
  | "degraded"
  | "disconnected"
  | "restarting"
  | "failed"

export interface DesktopRuntimeSnapshot {
  state: DesktopRuntimePhase
  detail: string
  backendUrl: string
  pid: number | null
  owned: boolean
  restartAttempts: number
}

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window
}

export async function getDesktopRuntime(): Promise<DesktopRuntimeSnapshot | null> {
  if (!isTauriRuntime()) return null
  const { invoke } = await import("@tauri-apps/api/core")
  return invoke<DesktopRuntimeSnapshot>("runtime_status")
}

export async function restartDesktopBackend(): Promise<DesktopRuntimeSnapshot | null> {
  if (!isTauriRuntime()) return null
  const { invoke } = await import("@tauri-apps/api/core")
  return invoke<DesktopRuntimeSnapshot>("restart_backend")
}

export async function showDesktopNotification(
  title: string,
  body: string,
): Promise<boolean> {
  if (!isTauriRuntime()) return false
  const { invoke } = await import("@tauri-apps/api/core")
  const result = await invoke<{ success: boolean }>("show_notification", {
    title,
    body,
  })
  return result.success
}

export async function openDesktopUrl(url: string): Promise<boolean> {
  if (!isTauriRuntime()) return false
  const { invoke } = await import("@tauri-apps/api/core")
  const result = await invoke<{ success: boolean }>("open_url", { url })
  return result.success
}

export async function listenForDesktopRuntime(
  listener: (snapshot: DesktopRuntimeSnapshot) => void,
): Promise<UnlistenFn> {
  if (!isTauriRuntime()) return () => {}
  const { listen } = await import("@tauri-apps/api/event")
  return listen<DesktopRuntimeSnapshot>("griffin://runtime-state", (event) => {
    listener(event.payload)
  })
}
