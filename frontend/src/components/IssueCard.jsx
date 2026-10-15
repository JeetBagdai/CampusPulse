import { useEffect, useState } from 'react'
import { CheckCircle2, Hand, ShieldCheck, Sparkles } from 'lucide-react'
import { api, hhmm, inr, num } from '../api'
import { TYPE_META, useStore } from '../store'
import { PriorityChip, SourceChip, TypeIcon } from './Icons'

const LANGS = [['en', 'EN'], ['hi', 'हिं'], ['kn', 'ಕನ್ನಡ']]
const STATUS_STYLE = {
  open: 'bg-rose-500/15 text-rose-300', assigned: 'bg-amber-500/15 text-amber-300',
  in_progress: 'bg-sky-500/15 text-sky-300', resolved: 'bg-sky-500/15 text-sky-300',
  verified: 'bg-emerald-500/15 text-emerald-300', auto_closed: 'bg-slate-500/15 text-slate-300',
  closed: 'bg-slate-500/15 text-slate-300',
}
const STATUS_LABEL = { resolved: 'verifying…', auto_closed: 'self-cleared', in_progress: 'in progress' }

export function StatusChip({ status }) {
  return <span className={`chip ${STATUS_STYLE[status] || ''}`}>{STATUS_LABEL[status] || status}</span>
}

export default function IssueCard({ issue, compact = false }) {
  const wo = useStore((s) => s.snap?.workorders?.[issue.wo])
  const openCopilot = useStore((s) => s.openCopilot)
  const select = useStore((s) => s.select)
  const [lang, setLang] = useState(null)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const meta = TYPE_META[issue.type] || {}
  const live = !['verified', 'auto_closed', 'closed'].includes(issue.status)

  useEffect(() => {
    if (!lang || !issue.wo) return
    let alive = true
    setMsg(null)
    api.get(`/api/workorders/${issue.wo}?lang=${lang}`).then((r) => alive && setMsg(r)).catch(() => {})
    return () => { alive = false }
  }, [lang, issue.wo, wo?.source])

  const act = async (fn) => { setBusy(true); try { await fn() } finally { setBusy(false) } }

  return (
    <div className="glass p-3 pop" style={{ borderLeft: `3px solid ${meta.color}` }}>
      <div className="flex items-start gap-2">
        <div className="w-8 h-8 rounded-xl well flex items-center justify-center shrink-0"><TypeIcon type={issue.type} size={16} /></div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold">{meta.label}</span>
            <button className="font-mono text-sm text-sky-300 hover:underline" onClick={() => select(issue.target)}>{issue.target}</button>
            <PriorityChip p={issue.priority} />
            <StatusChip status={issue.status} />
            {issue.escalated && <span className="chip !bg-rose-500/20 !text-rose-200">escalated</span>}
            {issue.reports_count > 1 && <span className="chip">{issue.reports_count} reports</span>}
          </div>
          <div className="text-sm text-slate-400 truncate">{issue.target_name} · {issue.location}</div>
        </div>
        <div className="text-right shrink-0">
          {issue.rate_inr_hr > 0 && <div className="text-sm text-rose-300 tabular-nums">{inr(issue.rate_inr_hr)}/h</div>}
          {issue.saved_inr > 0
            ? <div className="text-xs text-emerald-300">saved {inr(issue.saved_inr)}</div>
            : issue.loss_inr > 0 && <div className="text-xs text-slate-400">lost {inr(issue.loss_inr)}</div>}
        </div>
      </div>

      {!compact && (
        <>
          <div className="flex flex-wrap gap-1 mt-2 items-center">
            {issue.detected_by.map((d) => <SourceChip key={d} source={d} />)}
            <span className="text-xs text-slate-500 ml-auto">detected {hhmm(issue.created_at)}</span>
          </div>
          {issue.evidence?.description && <div className="text-sm text-slate-300 mt-2">“{issue.evidence.description}”</div>}
          {issue.type === 'WATER_LEAK' && issue.loss_l > 0 && <div className="text-xs text-slate-400 mt-1">{num(issue.loss_l)} L lost so far</div>}
          {issue.photo && <img src={issue.photo} alt="report" className="mt-2 rounded-lg max-h-40 object-cover" />}

          {wo && (
            <div className="mt-3 well p-2.5">
              <div className="flex items-center gap-x-2 gap-y-1 text-sm flex-wrap">
                <span className="font-mono text-blue-300">{wo.id}</span>
                <span className="text-slate-300">→ {wo.assignee}</span>
                <span className="ml-auto chip" title={wo.validator?.rejected_numbers ? `rejected: ${wo.validator.rejected_numbers}` : ''}>
                  {wo.source === 'llm' ? <><ShieldCheck size={12} className="text-blue-300" /> AI · numbers verified</> : 'template'}
                </span>
              </div>
              <div className="font-medium mt-1">{(wo.content[lang] || wo.content.en).title}</div>
              <div className="flex gap-1 mt-2">
                {LANGS.map(([code, label]) => (
                  <button key={code} className={`chip !text-[11px] !py-0 ${lang === code ? '!bg-blue-400/25 !text-blue-100' : ''}`}
                    onClick={() => setLang(lang === code ? null : code)}>{label}</button>
                ))}
                <span className="text-xs text-slate-500 ml-1 self-center">sent in {wo.lang.toUpperCase()}</span>
              </div>
              {lang && (
                <pre className="mt-2 whitespace-pre-wrap text-[13px] leading-snug font-sans text-slate-200 well p-2 max-h-64 overflow-auto">
                  {msg ? msg.message : 'Loading…'}
                </pre>
              )}
            </div>
          )}

          <div className="flex gap-2 mt-3 flex-wrap">
            {live && issue.status === 'assigned' && wo &&
              <button className="btn" disabled={busy} onClick={() => act(() => api.post(`/api/workorders/${wo.id}/ack`))}><Hand size={15} /> Noted</button>}
            {live && issue.status !== 'resolved' &&
              <button className="btn btn-primary" disabled={busy} onClick={() => act(() => api.post(`/api/issues/${issue.id}/resolve`))}>
                <CheckCircle2 size={15} /> Mark done</button>}
            <button className="btn" onClick={() => openCopilot(`Explain ${issue.id} at ${issue.target} and what we should do about it.`)}>
              <Sparkles size={15} /> Ask</button>
          </div>
        </>
      )}
    </div>
  )
}
