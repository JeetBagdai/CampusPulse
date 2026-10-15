// Work: an inbox of work orders on the left, the selected one in detail on the right.
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, MapPin, Sparkles } from 'lucide-react'
import { api, hhmm, inr } from '../api'
import { TYPE_META, useStore } from '../store'
import TelegramIcon from '../components/TelegramIcon'

const DONE = ['verified', 'auto_closed', 'closed']
const LANGS = [['en', 'English'], ['hi', 'हिन्दी'], ['kn', 'ಕನ್ನಡ']]
const KIND = { ENERGY_WASTE: 'Energy waste', WATER_LEAK: 'Water leak', BIN_OVERFLOW: 'Waste', LITTER: 'Litter', UNDERUSED_BOOKING: 'Underused booking' }

function title(i) {
  const n = i.target_name || i.target
  switch (i.type) {
    case 'ENERGY_WASTE': return `Lights on in empty ${n}`
    case 'WATER_LEAK': return `Water leak in ${n}`
    case 'BIN_OVERFLOW': return `Bin overflowing at ${n}`
    case 'LITTER': return `Litter reported at ${n}`
    case 'UNDERUSED_BOOKING': return `${n} booked but empty`
    default: return n
  }
}

function subline(i, wo) {
  if (i.status === 'resolved') return 'checking the fix'
  if (i.escalated) return 'escalated'
  if (DONE.includes(i.status)) return i.saved_inr > 0 ? `saved ${inr(i.saved_inr)}` : i.status === 'auto_closed' ? 'cleared by itself' : 'verified'
  return wo?.assignee || 'not assigned yet'
}

// 4 steps: detected, sent to staff, fixed, verified; returns how many are complete
function stepsDone(status) {
  return { open: 1, assigned: 2, in_progress: 2, resolved: 3, verified: 4, auto_closed: 4, closed: 4 }[status] ?? 1
}

function Steps({ issue, wo }) {
  const n = stepsDone(issue.status)
  const steps = [
    ['Detected', hhmm(issue.created_at)],
    ['Sent to staff', wo ? `${wo.assignee}` : 'pending'],
    ['Fixed', n > 2 ? 'staff tapped Done' : issue.status === 'in_progress' ? 'staff on it' : 'waiting for staff'],
    ['Verified', n > 3 ? (issue.status === 'auto_closed' ? 'cleared by itself' : 'confirmed') : 'next reading'],
  ]
  return (
    <ol aria-label="Progress" className="grid grid-cols-4 gap-2 mt-7">
      {steps.map(([label, sub], k) => {
        const state = k < n ? 'done' : k === n ? 'now' : 'todo'
        return (
          <li key={label} className="min-w-0">
            <div className="h-1 rounded-full bg-[#3a3a3a] overflow-hidden">
              <div className={`h-full bg-[#6ea0f5] ${state === 'done' ? 'w-full' : state === 'now' ? 'w-2/5 animate-pulse' : 'w-0'}`} />
            </div>
            <div className={`mt-2.5 text-[13px] font-semibold ${state === 'todo' ? 'text-neutral-500' : 'text-neutral-100'}`}>{label}</div>
            <div className="text-xs text-neutral-500 mt-0.5 truncate">{sub}</div>
          </li>
        )
      })}
    </ol>
  )
}

function Message({ wo, channel }) {
  const [lang, setLang] = useState(wo.lang || 'en')
  const [msg, setMsg] = useState(null)
  useEffect(() => {
    let alive = true
    setMsg(null)
    api.get(`/api/workorders/${wo.id}?lang=${lang}`).then((r) => alive && setMsg(r.message)).catch(() => {})
    return () => { alive = false }
  }, [wo.id, lang, wo.source])
  return (
    <div className="mt-7 rounded-2xl bg-[#1f1f1f] border border-white/[0.06] p-5">
      <div className="flex items-center gap-2.5 flex-wrap">
        <TelegramIcon size={22} />
        <span className="font-semibold">Sent to {wo.assignee}</span>
        <span className="text-neutral-500 text-[13px]">{channel === 'telegram' ? 'on Telegram' : 'in the app'}, {hhmm(wo.created_at)}</span>
        <div role="group" aria-label="Language" className="ml-auto flex gap-1">
          {LANGS.map(([code, label]) => (
            <button key={code} onClick={() => setLang(code)}
              className={`rounded-full px-3 py-1 text-xs font-semibold border transition
                ${lang === code ? 'border-[#6ea0f5]/50 bg-[#6ea0f5]/15 text-blue-100' : 'border-white/10 text-neutral-400 hover:text-neutral-200'}`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-4 text-[15px] leading-relaxed text-neutral-300 whitespace-pre-line min-h-[3rem]">{msg ?? 'Loading…'}</p>
    </div>
  )
}

function Detail({ issue }) {
  const wo = useStore((s) => s.snap?.workorders?.[issue.wo])
  const channel = useStore((s) => s.snap?.channel)
  const openCopilot = useStore((s) => s.openCopilot)
  const select = useStore((s) => s.select)
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const meta = TYPE_META[issue.type] || {}
  const live = !DONE.includes(issue.status)

  const done = async () => {
    setBusy(true)
    try { await api.post(`/api/issues/${issue.id}/resolve`) } finally { setBusy(false) }
  }

  return (
    <div className="pop">
      <div className="flex items-start gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="text-xs font-bold tracking-[0.08em] uppercase" style={{ color: meta.color }}>
            {KIND[issue.type] || meta.label}{issue.priority === 'P1' && live ? ' · Urgent' : ''}{issue.escalated && live ? ' · Escalated' : ''}
          </div>
          <h1 className="mt-1.5 text-2xl md:text-[30px] font-normal tracking-tight leading-tight">{title(issue)}</h1>
          <p className="mt-1.5 text-neutral-400">{issue.location} · detected {hhmm(issue.created_at)}</p>
        </div>
        <div className="ml-auto text-right">
          {issue.rate_inr_hr > 0 && <div className="text-[30px] font-light text-rose-400 tabular-nums">{inr(issue.rate_inr_hr)}/h</div>}
          {issue.saved_inr > 0 ? <div className="text-emerald-300 text-[13px]">{inr(issue.saved_inr)} saved</div>
            : issue.loss_inr > 0 && <div className="text-neutral-400 text-[13px]">{inr(issue.loss_inr)} lost so far</div>}
        </div>
      </div>

      <Steps issue={issue} wo={wo} />

      {issue.evidence?.description && <p className="mt-6 text-neutral-300">“{issue.evidence.description}”</p>}
      {issue.photo && <img src={issue.photo} alt="Reported photo" className="mt-4 rounded-xl max-h-52 object-cover" />}

      {wo && <Message key={wo.id} wo={wo} channel={channel} />}

      <div className="flex gap-2.5 mt-7 flex-wrap">
        {live && issue.status !== 'resolved' && (
          <button className="btn btn-primary !px-5 !py-3 !text-[15px]" disabled={busy} onClick={done}><CheckCircle2 size={16} /> Mark done</button>
        )}
        <button className="btn !px-5 !py-3 !text-[15px]" onClick={() => { select(issue.target); nav('/') }}><MapPin size={16} /> Show on map</button>
        <button className="btn !bg-transparent !border-transparent !text-[#8ab4f8] !px-2 !py-3 !text-[15px]"
          onClick={() => openCopilot(`Explain ${issue.id} at ${issue.target} and what we should do about it.`)}>
          <Sparkles size={16} /> Ask AI about this
        </button>
      </div>
    </div>
  )
}

export default function IssuesPage() {
  const snap = useStore((s) => s.snap)
  const [tab, setTab] = useState('open')
  const [selId, setSelId] = useState(null)
  const open = snap.issues.filter((i) => !DONE.includes(i.status))
  const done = snap.issues.filter((i) => DONE.includes(i.status))
  const list = tab === 'open' ? open : done
  const sel = list.find((i) => i.id === selId) || list[0]

  return (
    <div className="p-3 md:p-6 max-w-[1120px] mx-auto flex flex-wrap gap-5 items-start">
      <section aria-label="Work orders" className="flex-[1_1_320px] md:max-w-[380px] w-full rounded-[20px] bg-[#262626] border border-white/[0.06] overflow-hidden">
        <div className="flex gap-1 p-3 border-b border-white/[0.06]">
          {[['open', `Open ${open.length}`], ['done', `Done ${done.length}`]].map(([k, label]) => (
            <button key={k} onClick={() => { setTab(k); setSelId(null) }}
              className={`flex-1 rounded-[10px] py-2 text-sm transition ${tab === k ? 'bg-[#3a3a3a] text-white font-semibold' : 'text-neutral-400 hover:text-neutral-200'}`}>
              {label}
            </button>
          ))}
        </div>
        <div className="max-h-[calc(100vh-220px)] overflow-auto">
          {list.map((i) => {
            const active = sel?.id === i.id
            const meta = TYPE_META[i.type] || {}
            return (
              <button key={i.id} onClick={() => setSelId(i.id)}
                className={`w-full text-left flex items-center gap-3 px-4 py-3.5 border-t border-white/[0.04] transition
                  ${active ? 'bg-[#323232] shadow-[inset_3px_0_0_#6ea0f5]' : 'hover:bg-white/[0.03]'}`}>
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: meta.color }} />
                <span className="flex-1 min-w-0">
                  <span className="block font-semibold text-sm truncate">{title(i)}</span>
                  <span className="block text-xs text-neutral-400 mt-0.5 truncate">{i.location} · {subline(i, snap.workorders?.[i.wo])}</span>
                </span>
                {i.rate_inr_hr > 0 && tab === 'open' && <span className="text-[13px] font-semibold text-rose-400 tabular-nums">{inr(i.rate_inr_hr)}/h</span>}
              </button>
            )
          })}
          {!list.length && <div className="p-6 text-sm text-neutral-500">{tab === 'open' ? 'Nothing open. The campus is running clean.' : 'Nothing fixed yet.'}</div>}
        </div>
      </section>

      <section aria-label="Selected work order" className="flex-[999_1_560px] min-w-0 rounded-[20px] bg-[#262626] border border-white/[0.06] p-5 md:p-8">
        {sel ? <Detail key={sel.id} issue={sel} /> : <div className="text-neutral-500">Select a work order to see it here.</div>}
      </section>
    </div>
  )
}
