import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { Dog, Mic, MicOff, SendHorizonal, Sparkles } from "lucide-react"

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
  const suggestions = ["What’s on my agenda?", "Open my workspace", "Start a focus timer"]

  return (
    <GlassCard className="min-h-0 xl:col-span-2">
      <GlassCardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <GlassCardTitle className="flex items-center gap-2"><span className="brand-mark !h-7 !w-7 !rounded-lg"><Dog className="h-3.5 w-3.5" /></span><span>Gryphon chat</span><span className="sr-only">Chat</span></GlassCardTitle>
            <GlassCardDescription className="mt-2 text-muted-foreground">Your calm command line for the day.</GlassCardDescription>
          </div>
          <span className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[.14em] text-stone-400"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Ready</span>
        </div>
      </GlassCardHeader>
      <GlassCardContent className="flex min-h-0 flex-1 flex-col gap-4">
        <div
          ref={scrollRef}
          className="flex max-h-72 min-h-40 flex-col gap-3 overflow-y-auto pr-1"
          aria-label="Chat messages"
        >
          {messages.length === 0 ? (
            <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center">
              <span className="brand-mark !h-11 !w-11 rounded-2xl"><Dog className="h-5 w-5" /></span>
              <div>
                <p className="text-sm font-medium text-stone-200">What can I take off your paws?</p>
                <p className="mt-1 text-xs text-stone-500">Ask, dictate, or start with a quick action.</p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => setDraft(suggestion)} className="chat-suggestion rounded-full px-3 py-1.5 text-[11px] transition">{suggestion}</button>)}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "event-enter max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                  msg.role === "user"
                    ? "chat-message--user self-end"
                    : "chat-message--assistant self-start text-stone-200",
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
        <div className="flex items-center gap-2 rounded-2xl border border-white/[.08] bg-black/[.14] p-1.5 shadow-inner">
          <Input
            ref={inputRef}
            data-testid="chat-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Message Gryphon…"
            aria-label="Message Gryphon"
            disabled={busy}
            className="h-11 border-0 bg-transparent text-stone-100 shadow-none focus-visible:ring-0"
          />
          <Button
            type="button"
            size="icon"
            aria-label={voiceState === "listening" ? "Stop recording" : "Start voice input"}
            data-testid="mic-button"
            onClick={() => void toggleRecording()}
            disabled={busy}
            className={cn(
              "h-11 w-11 rounded-xl transition-all hover:brightness-110 active:scale-95",
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
            className="h-11 w-11 rounded-xl transition-all hover:brightness-110 active:scale-95"
          >
            {sending ? <Sparkles className="h-4 w-4 animate-pulse" /> : <SendHorizonal className="h-4 w-4" />}
          </Button>
        </div>
      </GlassCardContent>
    </GlassCard>
  )
}
