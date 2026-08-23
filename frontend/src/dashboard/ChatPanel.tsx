import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { CalendarDays, FileText, FolderOpen, Keyboard, Mic, MicOff, Paperclip, Play, SendHorizontal } from "lucide-react"

import { Input } from "@/components/ui/input"
import { useGriffinEvents } from "@/lib/useGriffinEvents"
import { sendChat, sendVoice } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ChatMessage } from "@/lib/types"
import { GriffinPresence } from "@/dashboard/GriffinPresence"

function newId(): string { return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `msg_${Date.now()}_${Math.random().toString(36).slice(2)}` }
type VoiceState = "idle" | "listening" | "transcribing"

export function ChatPanel() {
  const { sessionId, setSessionId, avatarState } = useGriffinEvents()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState("")
  const [sending, setSending] = useState(false)
  const [voiceState, setVoiceState] = useState<VoiceState>("idle")
  const [textInputOpen, setTextInputOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  useEffect(() => { if (textInputOpen) inputRef.current?.focus() }, [textInputOpen])
  useEffect(() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight }, [messages])
  useEffect(() => () => { if (recorderRef.current?.state !== "inactive") recorderRef.current?.stop() }, [])
  const pushMessage = (role: ChatMessage["role"], content: string, id?: string) => setMessages((previous) => [...previous, { id: id ?? newId(), role, content, createdAt: new Date().toISOString() }])
  const submit = async () => {
    const text = draft.trim(); if (!text || sending) return
    setSending(true); setDraft(""); setTextInputOpen(false); pushMessage("user", text)
    try { const response = await sendChat(text, sessionId); setSessionId(response.session_id); pushMessage("assistant", response.response, response.message_id) }
    catch (error) { pushMessage("assistant", error instanceof Error ? error.message : "Griffin could not complete that request.") }
    finally { setSending(false) }
  }
  const submitVoice = async (audio: Blob) => {
    setVoiceState("transcribing")
    try { const response = await sendVoice(audio, sessionId); setSessionId(response.session_id); pushMessage("user", response.transcript); pushMessage("assistant", response.response, response.message_id) }
    catch (error) { pushMessage("assistant", error instanceof Error ? error.message : "Voice input is unavailable.") }
    finally { setVoiceState("idle") }
  }
  const toggleRecording = async () => {
    if (voiceState === "listening") { recorderRef.current?.stop(); return }
    if (voiceState !== "idle" || typeof MediaRecorder === "undefined") return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder; chunksRef.current = []
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data) }
      recorder.onstop = () => { stream.getTracks().forEach((track) => track.stop()); void submitVoice(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" })) }
      recorder.start(); setVoiceState("listening")
    } catch { setVoiceState("idle") }
  }
  const thinking = sending || voiceState === "transcribing"
  const presenceState = voiceState === "listening" ? "LISTENING" : avatarState === "LISTENING" ? "IDLE" : avatarState
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => { if (event.key === "Enter") { event.preventDefault(); void submit() } }
  const useQuickAction = (prompt: string) => { setDraft(prompt); setTextInputOpen(true) }
  return <main className="griffin-conversation">
    <div className={cn("griffin-activity-line", (thinking || messages.some((message) => message.role === "assistant")) && "is-visible")} aria-hidden><span /></div>
    <section ref={scrollRef} className="griffin-message-canvas" aria-label="Chat messages">
      {messages.length === 0 && !thinking && <div className="griffin-welcome"><div><p className="griffin-greeting">Good evening.</p><p className="griffin-welcome__copy">What would you like to accomplish?</p></div><GriffinPresence state={presenceState} /></div>}
      {thinking && <div className="griffin-thinking" aria-label="Griffin is thinking" />}
      {messages.map((message) => <div key={message.id} className={cn("griffin-message", message.role === "user" ? "griffin-message--user" : "griffin-message--assistant")}>{message.content}</div>)}
    </section>
    <div className="griffin-input-zone">
      {menuOpen && <div className="griffin-speed-dial">
        <button type="button" className="griffin-fab griffin-fab--attach" aria-label="Attach a file" onClick={() => setMenuOpen(false)}><Paperclip /><span>Attach</span></button>
        <button type="button" className="griffin-fab griffin-fab--text" aria-label="Text input" onClick={() => { setTextInputOpen(true); setMenuOpen(false) }}><Keyboard /><span>Text input</span></button>
        <button type="button" className="griffin-fab griffin-fab--files" aria-label="Show all files" onClick={() => setMenuOpen(false)}><FileText /><span>Files</span></button>
      </div>}
      <div className={cn("griffin-text-entry", !textInputOpen && "griffin-text-entry--hidden")}><Input ref={inputRef} data-testid="chat-input" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={onKeyDown} placeholder="Message Griffin" aria-label="Message Griffin" disabled={thinking} /><button type="button" aria-label="Send message" onClick={() => void submit()} disabled={!draft.trim() || thinking}><SendHorizontal /></button></div>
      {!textInputOpen && !thinking && <div className="griffin-quick-actions" aria-label="Quick actions"><button type="button" onClick={() => useQuickAction("Plan my day")}> <CalendarDays aria-hidden />Plan my day</button><button type="button" onClick={() => useQuickAction("Open my project")}> <FolderOpen aria-hidden />Open project</button><button type="button" onClick={() => useQuickAction("Run a workflow")}> <Play aria-hidden />Run workflow</button></div>}
      <button type="button" className={cn("griffin-mic", voiceState === "listening" && "is-listening")} aria-label={voiceState === "listening" ? "Stop recording" : "Start voice input"} data-testid="mic-button" onClick={() => { if (!textInputOpen) setMenuOpen((open) => !open); else void toggleRecording() }} disabled={thinking}>{voiceState === "listening" ? <MicOff /> : <Mic />}</button>
    </div>
  </main>
}
