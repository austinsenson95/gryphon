import { Check, LoaderCircle, MessageCircle, Pencil, Send, X } from "lucide-react"
import { useState } from "react"

import { GlassCard, GlassCardContent, GlassCardHeader, GlassCardTitle } from "@/components/ui/glass-card"
import { approveWhatsAppAction, cancelWhatsAppAction, prepareWhatsAppAction, sendWhatsAppAction } from "@/lib/api"
import type { WhatsAppAction } from "@/lib/types"
import { useGriffinEvents } from "@/lib/useGriffinEvents"

function ActionCard({ action }: { action: WhatsAppAction }) {
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(action.message)
  const [error, setError] = useState<string | null>(null)
  const actionable = action.status === "approval_required"

  const send = async () => {
    setBusy(true); setError(null)
    try {
      const approved = await approveWhatsAppAction(action.action_id)
      await sendWhatsAppAction(action.action_id, approved.approval_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : "The message could not be sent.")
    } finally { setBusy(false) }
  }
  const cancel = async () => {
    setBusy(true); setError(null)
    try { await cancelWhatsAppAction(action.action_id) }
    catch (err) { setError(err instanceof Error ? err.message : "The draft could not be cancelled.") }
    finally { setBusy(false) }
  }
  const saveEdit = async () => {
    setBusy(true); setError(null)
    try {
      await cancelWhatsAppAction(action.action_id)
      await prepareWhatsAppAction(action.recipient, text)
      setEditing(false)
    } catch (err) { setError(err instanceof Error ? err.message : "The draft could not be updated.") }
    finally { setBusy(false) }
  }

  return <div className={`whatsapp-action is-${action.status}`} data-testid="whatsapp-action">
    <div className="whatsapp-action__rail" aria-hidden />
    <div className="whatsapp-action__body">
      <div className="whatsapp-action__recipient"><span>To</span><strong>{action.recipient}</strong><em>{action.status === "approval_required" ? "Needs your approval" : action.status}</em></div>
      {editing ? <textarea aria-label="WhatsApp message" value={text} onChange={(event) => setText(event.target.value)} autoFocus /> : <p>{action.message}</p>}
      {error && <div className="whatsapp-action__error" role="alert">{error}</div>}
      {action.status === "sent" && <div className="whatsapp-action__sent"><Check /> Sent once and recorded</div>}
      {action.status === "uncertain" && <div className="whatsapp-action__error" role="alert">Delivery could not be verified. Check WhatsApp before trying anything else.</div>}
      {actionable && <div className="whatsapp-action__controls">
        {editing ? <button type="button" onClick={() => void saveEdit()} disabled={busy}>Save new draft</button> : <button type="button" onClick={() => setEditing(true)} disabled={busy}><Pencil /> Edit</button>}
        <button type="button" onClick={() => void cancel()} disabled={busy}><X /> Cancel</button>
        {!editing && <button className="is-send" type="button" onClick={() => void send()} disabled={busy}>{busy ? <LoaderCircle className="animate-spin" /> : <Send />} Send</button>}
      </div>}
    </div>
  </div>
}

export function WhatsAppApprovalCard() {
  const { whatsAppActions } = useGriffinEvents()
  const visible = whatsAppActions.filter((action) => !["cancelled", "expired"].includes(action.status)).slice(0, 3)
  if (!visible.length) return null
  return <GlassCard className="whatsapp-card">
    <GlassCardHeader><div className="flex items-center justify-between"><GlassCardTitle>WhatsApp</GlassCardTitle><MessageCircle className="h-4 w-4 text-emerald-400" aria-hidden /></div></GlassCardHeader>
    <GlassCardContent className="space-y-3">{visible.map((action) => <ActionCard key={action.action_id} action={action} />)}</GlassCardContent>
  </GlassCard>
}
