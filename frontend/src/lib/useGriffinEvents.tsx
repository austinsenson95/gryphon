import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

import {
  ERROR_IDLE_MS,
  nextAvatarState,
  SUCCESS_IDLE_MS,
  type AvatarState,
} from "@/avatar/stateMachine"
import { getBrowserStatus, getEvents, getHealth, getProviderInfo, setProvider } from "@/lib/api"
import { createGriffinSocket } from "@/lib/ws"
import {
  getDesktopRuntime,
  listenForDesktopRuntime,
  restartDesktopBackend,
  type DesktopRuntimeSnapshot,
} from "@/lib/desktop"
import type {
  AppNotification,
  BrowserStatus,
  ConnectionStatus,
  CurrentTask,
  GriffinEvent,
  LLMProvider,
  ToolActivityItem,
} from "@/lib/types"

const EVENT_BUFFER_CAP = 200
const NOTIFICATION_TTL_MS = 6_000

export interface GriffinState {
  events: GriffinEvent[]
  connectionStatus: ConnectionStatus
  healthOk: boolean
  llmMode: "live" | "mock" | null
  provider: LLMProvider | null
  availableProviders: LLMProvider[]
  switchingProvider: boolean
  avatarState: AvatarState
  currentTask: CurrentTask | null
  toolActivity: ToolActivityItem[]
  browserStatus: BrowserStatus | null
  notifications: AppNotification[]
  sessionId: string | null
  desktopRuntime: DesktopRuntimeSnapshot | null
  setSessionId: (id: string) => void
  dismissNotification: (id: string) => void
  switchProvider: (provider: LLMProvider) => Promise<void>
  restartKernel: () => Promise<void>
}

const defaultState: GriffinState = {
  events: [],
  connectionStatus: "connecting",
  healthOk: false,
  llmMode: null,
  provider: null,
  availableProviders: ["ollama", "xai"],
  switchingProvider: false,
  avatarState: "IDLE",
  currentTask: null,
  toolActivity: [],
  browserStatus: null,
  notifications: [],
  sessionId: null,
  desktopRuntime: null,
  setSessionId: () => {},
  dismissNotification: () => {},
  switchProvider: async () => {},
  restartKernel: async () => {},
}

const GriffinContext = createContext<GriffinState>(defaultState)

/** Access the shared Griffin event/state store. */
export function useGriffinEvents(): GriffinState {
  return useContext(GriffinContext)
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined
}

function toolNameOf(event: GriffinEvent): string {
  return asString(event.data.tool) ?? asString(event.data.name) ?? "unknown tool"
}

function toolArgsOf(event: GriffinEvent): Record<string, unknown> | undefined {
  const input = event.data.input ?? event.data.arguments
  if (input !== null && typeof input === "object" && !Array.isArray(input)) {
    return input as Record<string, unknown>
  }
  return undefined
}

function errorMessageOf(event: GriffinEvent, fallback: string): string {
  if (typeof event.data.error === "string") return event.data.error
  if (event.data.error && typeof event.data.error === "object" && !Array.isArray(event.data.error)) {
    const message = (event.data.error as Record<string, unknown>).message
    if (typeof message === "string") return message
  }
  return asString(event.data.message) ?? fallback
}

export function GriffinProvider({ children }: { children: ReactNode }) {
  const [events, setEvents] = useState<GriffinEvent[]>([])
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("connecting")
  const [healthOk, setHealthOk] = useState(false)
  const [llmMode, setLlmMode] = useState<"live" | "mock" | null>(null)
  const [provider, setProviderState] = useState<LLMProvider | null>(null)
  const [availableProviders, setAvailableProviders] = useState<LLMProvider[]>([
    "ollama",
    "xai",
  ])
  const [switchingProvider, setSwitchingProvider] = useState(false)
  const [avatarState, setAvatarState] = useState<AvatarState>("IDLE")
  const [currentTask, setCurrentTask] = useState<CurrentTask | null>(null)
  const [toolActivity, setToolActivity] = useState<ToolActivityItem[]>([])
  const [browserStatus, setBrowserStatus] = useState<BrowserStatus | null>(null)
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [desktopRuntime, setDesktopRuntime] =
    useState<DesktopRuntimeSnapshot | null>(null)

  const seenIds = useRef(new Set<string>())
  const avatarTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const dismissNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }, [])

  const pushNotification = useCallback(
    (notification: AppNotification) => {
      setNotifications((prev) => [...prev, notification])
      setTimeout(() => dismissNotification(notification.id), NOTIFICATION_TTL_MS)
    },
    [dismissNotification],
  )

  const applyAvatarEvent = useCallback((event: GriffinEvent) => {
    const next = nextAvatarState(event)
    if (!next) return
    if (avatarTimer.current) {
      clearTimeout(avatarTimer.current)
      avatarTimer.current = null
    }
    setAvatarState(next)
    if (next === "SUCCESS" || next === "ERROR") {
      const delay = next === "SUCCESS" ? SUCCESS_IDLE_MS : ERROR_IDLE_MS
      avatarTimer.current = setTimeout(() => setAvatarState("IDLE"), delay)
    }
  }, [])

  const handleEvent = useCallback(
    (event: GriffinEvent, isReplay = false) => {
      if (seenIds.current.has(event.id)) return
      seenIds.current.add(event.id)

      setEvents((prev) => [event, ...prev].slice(0, EVENT_BUFFER_CAP))
      applyAvatarEvent(event)

      switch (event.type) {
        case "SESSION_CREATED": {
          if (event.session_id) setSessionId(event.session_id)
          break
        }
        case "TASK_STARTED": {
          setCurrentTask({
            id: event.task_id ?? event.id,
            status: "running",
            input: asString(event.data.input) ?? asString(event.data.message),
          })
          break
        }
        case "TASK_COMPLETED": {
          setCurrentTask((prev) =>
            prev && (prev.id === event.task_id || event.task_id === null)
              ? {
                  ...prev,
                  status: "completed",
                  result:
                    asString(event.data.result) ??
                    asString(event.data.response) ??
                    prev.result,
                }
              : prev,
          )
          break
        }
        case "TASK_FAILED": {
          setCurrentTask((prev) =>
            prev && (prev.id === event.task_id || event.task_id === null)
              ? {
                  ...prev,
                  status: "failed",
                  result: errorMessageOf(event, "Task failed"),
                }
              : prev,
          )
          if (!isReplay) {
            pushNotification({
              id: `notif_${event.id}`,
              level: "error",
              title: "Task failed",
              body: errorMessageOf(event, "Griffin could not finish the task."),
            })
          }
          break
        }
        case "STT_FAILED": {
          if (!isReplay) {
            pushNotification({
              id: `notif_${event.id}`,
              level: "error",
              title: "Voice input failed",
              body: errorMessageOf(event, "Griffin could not understand the recording."),
            })
          }
          break
        }
        case "PHONE_CALL_COMPLETED": {
          if (!isReplay) {
            const call = event.data.call && typeof event.data.call === "object" && !Array.isArray(event.data.call)
              ? event.data.call as Record<string, unknown>
              : {}
            pushNotification({
              id: `notif_${event.id}`,
              level: "info",
              title: `Call with ${asString(call.contact_name) ?? "contact"} finished`,
              body: asString(call.summary) ?? "Open Calls to review the findings and transcript.",
            })
          }
          break
        }
        case "PHONE_CALL_FAILED": {
          if (!isReplay) {
            const call = event.data.call && typeof event.data.call === "object" && !Array.isArray(event.data.call)
              ? event.data.call as Record<string, unknown>
              : {}
            pushNotification({
              id: `notif_${event.id}`,
              level: "error",
              title: "Phone call failed",
              body: asString(call.error) ?? "Open Calls for details.",
            })
          }
          break
        }
        case "PERMISSION_REQUIRED":
        case "USER_APPROVAL_REQUIRED": {
          if (!isReplay) {
            pushNotification({
              id: `notif_${event.id}`,
              level: "warning",
              title: "Approval required",
              body:
                asString(event.data.message) ??
                `Griffin wants to run ${toolNameOf(event)}.`,
            })
          }
          break
        }
        case "BROWSER_NAVIGATION":
        case "BROWSER_PAGE_LOADED": {
          const url = asString(event.data.url)
          const title = asString(event.data.title)
          setBrowserStatus({
            active: Boolean(url),
            mock: false,
            url: url ?? null,
            title: title ?? null,
          })
          break
        }
        case "TOOL_CALL_STARTED": {
          if (toolNameOf(event).startsWith("browser.")) {
            setBrowserStatus((prev) => prev ?? { active: false, mock: false, url: null, title: null })
          }
          setToolActivity((prev) =>
            [
              {
                id: event.id,
                name: toolNameOf(event),
                args: toolArgsOf(event),
                success: null,
                timestamp: event.timestamp,
              },
              ...prev,
            ].slice(0, 50),
          )
          break
        }
        case "TOOL_CALL_COMPLETED":
        case "TOOL_CALL_FAILED": {
          const success = event.type === "TOOL_CALL_COMPLETED"
          const name = toolNameOf(event)
          setToolActivity((prev) => {
            const idx = prev.findIndex(
              (t) => t.success === null && t.name === name,
            )
            if (idx === -1) {
              return [
                {
                  id: event.id,
                  name,
                  args: toolArgsOf(event),
                  success,
                  timestamp: event.timestamp,
                },
                ...prev,
              ].slice(0, 50)
            }
            const nextList = [...prev]
            nextList[idx] = { ...nextList[idx], success }
            return nextList
          })
          break
        }
        default:
          break
      }
    },
    [applyAvatarEvent, pushNotification],
  )

  // Health check + provider info -> connection dot + llm mode badge
  const refreshHealth = useCallback(async () => {
    try {
      const health = await getHealth()
      setHealthOk(health.status === "ok")
      setLlmMode(health.llm_mode ?? null)
    } catch {
      setHealthOk(false)
    }
  }, [])

  const switchProvider = useCallback(
    async (next: LLMProvider) => {
      if (switchingProvider || next === provider) return
      setSwitchingProvider(true)
      try {
        const info = await setProvider(next)
        setProviderState(info.provider)
        setAvailableProviders(info.available)
        setLlmMode(info.mode)
        await refreshHealth()
      } catch (err) {
        pushNotification({
          id: `notif_provider_switch_${Date.now()}`,
          level: "error",
          title: "Provider switch failed",
          body: err instanceof Error ? err.message : "Could not switch LLM provider.",
        })
      } finally {
        setSwitchingProvider(false)
      }
    },
    [provider, switchingProvider, refreshHealth, pushNotification],
  )

  const restartKernel = useCallback(async () => {
    try {
      const snapshot = await restartDesktopBackend()
      if (snapshot) setDesktopRuntime(snapshot)
      await refreshHealth()
    } catch (err) {
      pushNotification({
        id: `notif_kernel_restart_${Date.now()}`,
        level: "error",
        title: "Kernel restart failed",
        body:
          err instanceof Error
            ? err.message
            : "Could not restart Griffin Kernel.",
      })
    }
  }, [pushNotification, refreshHealth])

  useEffect(() => {
    let cancelled = false
    let unlisten: (() => void) | undefined
    void (async () => {
      const cleanup = await listenForDesktopRuntime((snapshot) => {
        if (!cancelled) setDesktopRuntime(snapshot)
      })
      if (cancelled) {
        cleanup()
        return
      }
      unlisten = cleanup
      const snapshot = await getDesktopRuntime()
      if (!cancelled && snapshot) setDesktopRuntime(snapshot)
    })()
    return () => {
      cancelled = true
      unlisten?.()
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([getHealth(), getProviderInfo(), getBrowserStatus()])
      .then(([health, info, browser]) => {
        if (cancelled) return
        setHealthOk(health.status === "ok")
        setLlmMode(health.llm_mode ?? null)
        setProviderState(info.provider)
        setAvailableProviders(info.available)
        setBrowserStatus(browser)
      })
      .catch(() => {
        if (!cancelled) setHealthOk(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => void refreshHealth(), 5_000)
    return () => window.clearInterval(timer)
  }, [refreshHealth])

  // Seed the buffer from REST, then stream live events over WS
  useEffect(() => {
    let cancelled = false
    getEvents(50)
      .then((recent) => {
        if (cancelled) return
        // /api/events is chronological. Apply oldest -> newest so derived UI
        // state reflects the latest event; reversing this left Griffin showing
        // stale historical failures after a page load.
        recent.forEach((event) => handleEvent(event, true))
      })
      .catch(() => {
        // backend not up yet — WS reconnect loop keeps trying
      })
    const socket = createGriffinSocket({
      onEvent: (event) => handleEvent(event),
      onStatus: setConnectionStatus,
    })
    return () => {
      cancelled = true
      socket.close()
    }
  }, [handleEvent])

  // Clean up avatar decay timer on unmount
  useEffect(
    () => () => {
      if (avatarTimer.current) clearTimeout(avatarTimer.current)
    },
    [],
  )

  const value = useMemo<GriffinState>(
    () => ({
      events,
      connectionStatus,
      healthOk,
      llmMode,
      provider,
      availableProviders,
      switchingProvider,
      avatarState,
      currentTask,
      toolActivity,
      browserStatus,
      notifications,
      sessionId,
      desktopRuntime,
      setSessionId,
      dismissNotification,
      switchProvider,
      restartKernel,
    }),
    [
      events,
      connectionStatus,
      healthOk,
      llmMode,
      provider,
      availableProviders,
      switchingProvider,
      avatarState,
      currentTask,
      toolActivity,
      browserStatus,
      notifications,
      sessionId,
      desktopRuntime,
      dismissNotification,
      switchProvider,
      restartKernel,
    ],
  )

  return (
    <GriffinContext.Provider value={value}>{children}</GriffinContext.Provider>
  )
}
