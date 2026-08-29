import {
  BookUser,
  AudioLines,
  Check,
  ChevronRight,
  CircleStop,
  Clock3,
  ContactRound,
  LoaderCircle,
  MessageSquareText,
  PhoneCall as PhoneCallIcon,
  Plus,
  Radio,
  Send,
  Signal,
  ShieldCheck,
  Sparkles,
  UserRoundPlus,
  X,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react"

import {
  addPhoneContact,
  cancelPhoneCall,
  getPhoneCalls,
  getPhoneContacts,
  getPhoneStatus,
  startPhoneCall,
} from "@/lib/api"
import type { PhoneCall, PhoneContact, PhoneStatus } from "@/lib/types"
import { useGriffinEvents } from "@/lib/useGriffinEvents"
import { cn } from "@/lib/utils"

const ACTIVE = new Set(["queued", "ringing", "active"])

function timeLabel(value: string | null): string {
  if (!value) return "—"
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(value))
}

function durationLabel(call: PhoneCall): string {
  if (call.duration_seconds != null) {
    const minutes = Math.floor(call.duration_seconds / 60)
    const seconds = call.duration_seconds % 60
    return `${minutes}:${seconds.toString().padStart(2, "0")}`
  }
  if (!call.answered_at) return "—"
  const end = call.ended_at ? new Date(call.ended_at).getTime() : Date.now()
  const seconds = Math.max(0, Math.floor((end - new Date(call.answered_at).getTime()) / 1000))
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, "0")}`
}

function StatusMark({ status }: { status: PhoneCall["status"] }) {
  const live = ACTIVE.has(status)
  return <span className={cn("phone-status-mark", `is-${status}`)}><span />{live && status === "active" ? "Live" : status}</span>
}

function SignalWave({ active }: { active: boolean }) {
  return <div className={cn("phone-signal-wave", active && "is-active")} aria-hidden>
    {Array.from({ length: 23 }, (_, index) => <span key={index} style={{ "--signal-index": index, "--signal-height": `${22 + ((index * 37) % 66)}%` } as CSSProperties} />)}
  </div>
}

function AddContact({ onAdded, onClose }: { onAdded: (contact: PhoneContact) => void; onClose?: () => void }) {
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [notes, setNotes] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim() || !phone.trim() || busy) return
    setBusy(true); setError("")
    try {
      const contact = await addPhoneContact({ name, phone_number: phone, notes })
      onAdded(contact); setName(""); setPhone(""); setNotes(""); onClose?.()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save this contact.")
    } finally { setBusy(false) }
  }
  return <form className="phone-contact-form" onSubmit={(event) => void submit(event)}>
    <div className="phone-form-heading"><div><UserRoundPlus /><span>Add contact</span></div>{onClose && <button type="button" aria-label="Close add contact" onClick={onClose}><X /></button>}</div>
    <label>Name<input aria-label="Contact name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Rahul" /></label>
    <label>Phone number<input aria-label="Phone number" aria-describedby="phone-allowlist-note" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+91 98765 43210" inputMode="tel" /></label>
    <p id="phone-allowlist-note" className="phone-allowlist-note"><ShieldCheck />Saving authorizes this number for Griffin calls. Indian 10-digit mobile numbers automatically receive +91.</p>
    <label>Notes<input aria-label="Contact notes" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Friend · prefers evening calls" /></label>
    {error && <p role="alert" className="phone-inline-error">{error}</p>}
    <button className="phone-primary-action" type="submit" disabled={busy || !name.trim() || !phone.trim()}>{busy ? <LoaderCircle className="animate-spin" /> : <ShieldCheck />}Save &amp; authorize</button>
  </form>
}

export function PhoneCallDashboard() {
  const { events, sessionId } = useGriffinEvents()
  const [contacts, setContacts] = useState<PhoneContact[]>([])
  const [calls, setCalls] = useState<PhoneCall[]>([])
  const [status, setStatus] = useState<PhoneStatus | null>(null)
  const [selectedContact, setSelectedContact] = useState("")
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null)
  const [mission, setMission] = useState("")
  const [questions, setQuestions] = useState("")
  const [showContactForm, setShowContactForm] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [error, setError] = useState("")

  const refresh = useCallback(async () => {
    const [nextContacts, nextCalls, nextStatus] = await Promise.all([getPhoneContacts(), getPhoneCalls(), getPhoneStatus()])
    setContacts(nextContacts); setCalls(nextCalls); setStatus(nextStatus)
    setSelectedContact((current) => current || nextContacts[0]?.name || "")
    setSelectedCallId((current) => current && nextCalls.some((call) => call.id === current) ? current : nextCalls[0]?.id ?? null)
  }, [])

  useEffect(() => { void refresh().catch(() => setError("Phone operations are unavailable.")) }, [refresh])
  const latestPhoneEvent = events.find((event) => event.type.startsWith("PHONE_CALL_"))?.id
  useEffect(() => { if (latestPhoneEvent) void refresh() }, [latestPhoneEvent, refresh])
  useEffect(() => {
    if (!calls.some((call) => ACTIVE.has(call.status))) return
    const timer = window.setInterval(() => void refresh(), 2_000)
    return () => window.clearInterval(timer)
  }, [calls, refresh])

  const selectedCall = useMemo(() => calls.find((call) => call.id === selectedCallId) ?? calls[0] ?? null, [calls, selectedCallId])
  const findings = selectedCall ? Object.values(selectedCall.findings).filter((value) => value && typeof value === "object" && "answer" in value) : []
  const lineReady = status?.mode === "live" && status.public_url_configured

  const launch = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedContact || !mission.trim() || launching) return
    setLaunching(true); setError("")
    try {
      const call = await startPhoneCall({
        contact_name: selectedContact,
        mission: mission.trim(),
        questions: questions.split("\n").map((value) => value.trim()).filter(Boolean),
        session_id: sessionId,
      })
      setCalls((current) => [call, ...current.filter((value) => value.id !== call.id)])
      setSelectedCallId(call.id); setMission(""); setQuestions("")
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the call.")
    } finally { setLaunching(false) }
  }

  const stop = async () => {
    if (!selectedCall || !ACTIVE.has(selectedCall.status)) return
    try { const call = await cancelPhoneCall(selectedCall.id); setCalls((current) => current.map((value) => value.id === call.id ? call : value)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not stop the call.") }
  }

  return <main className="phone-ops" aria-label="Phone missions">
    <section className="phone-ops__masthead">
      <div><p className="phone-eyebrow"><Radio />Outbound intelligence</p><h1>Calls</h1><p>Send Griffin to ask, listen, and return with the facts.</p></div>
      <div className="phone-line-state"><span className={cn(lineReady && "is-live")} /><div><strong>{lineReady ? "Vobiz line ready" : status?.mode === "live" ? "Vobiz needs a tunnel" : "Safe mock line"}</strong><small>{lineReady ? "Outbound calling enabled" : status?.mode === "live" ? "Start ngrok or set PHONE_PUBLIC_URL" : "Add phone credentials to dial"}</small></div></div>
    </section>

    <div className="phone-ops__grid">
      <aside className="phone-module phone-contacts-module">
        <div className="phone-module__heading"><div><BookUser /><span>Contacts</span></div><button type="button" aria-label="Add contact" onClick={() => setShowContactForm((value) => !value)}><Plus /></button></div>
        {showContactForm && <AddContact onAdded={(contact) => { setContacts((current) => [...current, contact]); setSelectedContact(contact.name) }} onClose={() => setShowContactForm(false)} />}
        <div className="phone-contact-list">
          {contacts.map((contact) => <button type="button" key={contact.id} className={cn("phone-contact", selectedContact === contact.name && "is-selected")} onClick={() => setSelectedContact(contact.name)}>
            <span className="phone-contact__avatar">{contact.name.slice(0, 1).toUpperCase()}</span><span><strong>{contact.name}</strong><small>{contact.phone_number}{contact.notes ? ` · ${contact.notes}` : ""}</small><em><ShieldCheck />Authorized for calls</em></span><ChevronRight />
          </button>)}
          {!contacts.length && !showContactForm && <div className="phone-empty"><ContactRound /><p>No contacts yet.</p><button type="button" onClick={() => setShowContactForm(true)}>Add the first contact</button></div>}
        </div>
        <form className="phone-mission-form" onSubmit={(event) => void launch(event)}>
          <div className="phone-module__heading"><div><Sparkles /><span>New mission</span></div></div>
          <label>Call<select aria-label="Contact to call" value={selectedContact} onChange={(event) => setSelectedContact(event.target.value)}><option value="">Choose a contact</option>{contacts.map((contact) => <option key={contact.id}>{contact.name}</option>)}</select></label>
          <label>Mission<textarea aria-label="Call mission" value={mission} onChange={(event) => setMission(event.target.value)} placeholder="Find out which dates work for the Goa trip." rows={3} /></label>
          <label>Questions <span>one per line · optional</span><textarea aria-label="Call questions" value={questions} onChange={(event) => setQuestions(event.target.value)} placeholder={"Which weekends work?\nWhat budget feels comfortable?"} rows={3} /></label>
          {error && <p role="alert" className="phone-inline-error">{error}</p>}
          <button data-testid="launch-call" className="phone-primary-action" disabled={!selectedContact || !mission.trim() || launching}>{launching ? <LoaderCircle className="animate-spin" /> : <PhoneCallIcon />}Initiate call</button>
        </form>
      </aside>

      <section className="phone-module phone-live-module">
        <div className="phone-module__heading"><div><Signal /><span>Live channel</span></div>{selectedCall && <StatusMark status={selectedCall.status} />}</div>
        {selectedCall ? <>
          <div className="phone-live-hero">
            <div className="phone-live-identity"><span>{selectedCall.contact_name.slice(0, 1).toUpperCase()}</span><div><p>{selectedCall.contact_name}</p><small>{selectedCall.phone_number}</small></div></div>
            <div className="phone-call-clock"><Clock3 /><span>{durationLabel(selectedCall)}</span></div>
          </div>
          <SignalWave active={selectedCall.status === "active"} />
          <div className="phone-mission-strip"><span>Mission</span><p>{selectedCall.mission}</p></div>
          <div className="phone-transcript" aria-label="Call transcript">
            {selectedCall.transcript.map((turn, index) => <article key={`${turn.timestamp}-${index}`} className={cn("phone-turn", turn.speaker === "assistant" && "is-griffin")}><div><strong>{turn.speaker === "assistant" ? "Griffin" : selectedCall.contact_name}</strong><time>{timeLabel(turn.timestamp)}</time></div><p>{turn.text}</p></article>)}
            {!selectedCall.transcript.length && <div className="phone-empty phone-empty--transcript"><AudioLines /><p>{ACTIVE.has(selectedCall.status) ? "Waiting for the line to connect…" : "No transcript was captured."}</p></div>}
          </div>
          {ACTIVE.has(selectedCall.status) && <button className="phone-stop-action" type="button" onClick={() => void stop()}><CircleStop />End call</button>}
        </> : <div className="phone-empty phone-empty--large"><PhoneCallIcon /><p>No calls yet.</p><span>Choose a contact and give Griffin a mission.</span></div>}
      </section>

      <aside className="phone-ops__right">
        <section className="phone-module phone-findings-module">
          <div className="phone-module__heading"><div><MessageSquareText /><span>Findings</span></div>{selectedCall?.status === "completed" && <Check />}</div>
          {selectedCall?.summary && <p className="phone-summary">{selectedCall.summary}</p>}
          <div className="phone-findings-list">{findings.map((finding, index) => <div key={index}><span>{finding.question}</span><p>{finding.answer}</p></div>)}</div>
          {!findings.length && <div className="phone-empty"><Send /><p>Findings arrive here after Griffin gets an answer.</p></div>}
        </section>
        <section className="phone-module phone-history-module">
          <div className="phone-module__heading"><div><Clock3 /><span>Call log</span></div><small>{calls.length}</small></div>
          <div className="phone-history-list">{calls.map((call) => <button key={call.id} type="button" className={cn(selectedCall?.id === call.id && "is-selected")} onClick={() => setSelectedCallId(call.id)}><span className={cn("phone-history-dot", `is-${call.status}`)} /><span><strong>{call.contact_name}</strong><small>{timeLabel(call.created_at)} · {call.status}</small></span><ChevronRight /></button>)}</div>
        </section>
      </aside>
    </div>
  </main>
}
