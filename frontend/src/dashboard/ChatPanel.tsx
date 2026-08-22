import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { Mic, MicOff, SendHorizonal } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  GlassCard,
  GlassCardContent,
  GlassCardDescription,
  GlassCardHeader,
  GlassCardTitle,
} from "@/components/ui/glass-card"
import { Input } from "@/components/ui/input"
import { AVATAR_ACTIVATE_EVENT } from "@/avatar/AvatarRenderer"
import { useGryphonEvents } from "@/lib/useGryphonEvents"
import { sendChat, sendVoice } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ChatMessage } from "@/lib/types"

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `msg_${Date.now()}_${Math.random().toString(36).slice(2)}`
}

type VoiceState = "idle" | "listening" | "transcribing"

const VOICE_LABEL: Record<VoiceState, string | null> = {
  idle: null,
  listening: "🎙 Listening… tap the mic again to stop",
  transcribing: "✍️ Transcribing…",
}

export function ChatPanel() {
  const { sessionId, setSessionId } = useGryphonEvents()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState("")
  const [sending, setSending] = useState(false)
  const [voiceState, setVoiceState] = useState<VoiceState>("idle")
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  // Avatar click focuses the chat input (kept decoupled via a window event).
  useEffect(() => {
    const focus = () => inputRef.current?.focus()
    window.addEventListener(AVATAR_ACTIVATE_EVENT, focus)
    return () => window.removeEventListener(AVATAR_ACTIVATE_EVENT, focus)
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  useEffect(
    () => () => {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop()
      }
    },
    [],
  )

  function pushMessage(role: ChatMessage["role"], content: string, id?: string) {
    setMessages((prev) => [
      ...prev,
      { id: id ?? newId(), role, content, createdAt: new Date().toISOString() },
    ])
  }

  async function submit() {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    setDraft("")
    pushMessage("user", text)
    try {
      const res = await sendChat(text, sessionId)
      setSessionId(res.session_id)
      pushMessage("assistant", res.response, res.message_id)
    } catch (err) {
      pushMessage(
        "assistant",
        `⚠️ ${err instanceof Error ? err.message : "Failed to reach Gryphon."}`,
      )
    } finally {
      setSending(false)
    }
  }

  async function toggleRecording() {
    if (voiceState === "listening") {
      recorderRef.current?.stop() // onstop handler continues the pipeline
      return
    }
    if (voiceState !== "idle") return
    if (typeof MediaRecorder === "undefined") {
      pushMessage("assistant", "⚠️ This browser doesn't support microphone recording.")
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        })
        void submitVoice(blob)
      }
      recorder.start()
      setVoiceState("listening")
    } catch {
      pushMessage("assistant", "⚠️ Microphone access was denied.")
      setVoiceState("idle")
    }
  }

  async function submitVoice(audio: Blob) {
    setVoiceState("transcribing")
    try {
      const res = await sendVoice(audio, sessionId)
      setSessionId(res.session_id)
      pushMessage("user", `🎙 ${res.transcript}`)
      pushMessage("assistant", res.response, res.message_id)
    } catch (err) {
      pushMessage(
        "assistant",
        `⚠️ ${err instanceof Error ? err.message : "Voice request failed."}`,
      )
    } finally {
      setVoiceState("idle")
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void submit()
    }
  }

  const busy = sending || voiceState === "transcribing"

  return (
    <GlassCard className="min-h-0">
      <GlassCardHeader>
        <GlassCardTitle>Chat</GlassCardTitle>
        <GlassCardDescription className="text-muted-foreground">
          Talk to Gryphon.
        </GlassCardDescription>
      </GlassCardHeader>
      <GlassCardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <div
          ref={scrollRef}
          className="flex max-h-64 min-h-32 flex-col gap-2 overflow-y-auto pr-1"
          aria-label="Chat messages"
        >
          {messages.length === 0 ? (
            <div className="flex min-h-32 flex-col items-center justify-center gap-2 text-center">
              <p className="text-sm text-white/70">
                Ask Gryphon anything — try “Open GitHub” or tap the mic and say it.
              </p>
              <p className="text-xs text-white/50">
                Replies appear here as Gryphon works.
              </p>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "event-enter max-w-[85%] whitespace-pre-wrap break-words rounded-xl px-3 py-2 text-sm leading-relaxed",
                  msg.role === "user"
                    ? "self-end bg-primary/90 text-primary-foreground shadow-[0_4px_16px_rgba(2,8,23,0.3)]"
                    : "self-start border border-white/10 bg-white/[0.09] text-white/90",
                )}
              >
                {msg.content}
              </div>
            ))
          )}
        </div>
        {VOICE_LABEL[voiceState] && (
          <p
            className={cn(
              "text-xs",
              voiceState === "listening" ? "text-red-300" : "text-cyan-200/80",
            )}
            role="status"
          >
            {VOICE_LABEL[voiceState]}
          </p>
        )}
        <div className="h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
        <div className="flex items-center gap-2">
          <Input
            ref={inputRef}
            data-testid="chat-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Message Gryphon…"
            aria-label="Message Gryphon"
            disabled={busy}
            className="h-11 rounded-xl border-white/15 bg-slate-950/40 text-white/90 backdrop-blur-sm transition-[border-color,box-shadow] placeholder:text-white/50 focus-visible:border-cyan-200/40 focus-visible:ring-1 focus-visible:ring-cyan-300/40 focus-visible:ring-offset-0"
          />
          <Button
            type="button"
            size="icon"
            aria-label={voiceState === "listening" ? "Stop recording" : "Start voice input"}
            data-testid="mic-button"
            onClick={() => void toggleRecording()}
            disabled={busy}
            className={cn(
              "h-11 w-11 rounded-xl shadow-[0_4px_16px_rgba(2,8,23,0.35)] transition-all hover:brightness-110 active:scale-95",
              voiceState === "listening" &&
                "bg-red-500/80 hover:bg-red-500 animate-pulse",
            )}
          >
            {voiceState === "listening" ? (
              <MicOff className="h-4 w-4" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </Button>
          <Button
            type="button"
            size="icon"
            aria-label="Send message"
            onClick={() => void submit()}
            disabled={busy || draft.trim() === ""}
            className="h-11 w-11 rounded-xl shadow-[0_4px_16px_rgba(2,8,23,0.35)] transition-all hover:brightness-110 active:scale-95"
          >
            <SendHorizonal className="h-4 w-4" />
          </Button>
        </div>
      </GlassCardContent>
    </GlassCard>
  )
}
