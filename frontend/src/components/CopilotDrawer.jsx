import { useEffect, useRef, useState } from 'react'
import { Loader2, Send, ShieldAlert, ShieldCheck, Sparkles, Wrench, X } from 'lucide-react'
import { api } from '../api'
import { useStore } from '../store'

const SUGGEST = [
  'Which building wastes the most energy today, and why?',
  'What would auto-off after 10 minutes plus LED retrofit save per month?',
  'List open issues that need urgent attention.',
  'How much water did we lose to leaks this week?',
]

function render(text) {
  return text.split('\n').map((line, i) => {
    const safe = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const html = safe.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/^[-*]\s+/, '• ')
    return <div key={i} dangerouslySetInnerHTML={{ __html: html || '&nbsp;' }} />
  })
}

export default function CopilotDrawer() {
  const { copilotOpen, copilotSeed, closeCopilot } = useStore()
  const [msgs, setMsgs] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef(null)

  const ask = async (q) => {
    const next = [...msgs, { role: 'user', content: q }]
    setMsgs(next)
    setBusy(true)
    try {
      const r = await api.post('/api/copilot', { messages: next.map(({ role, content }) => ({ role, content })) })
      setMsgs([...next, { role: 'assistant', content: r.reply, tools: r.tools, verified: r.verified, bad: r.unverified_numbers }])
    } catch (e) {
      setMsgs([...next, { role: 'assistant', content: `Error: ${e.message}` }])
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { if (copilotOpen && copilotSeed) ask(copilotSeed) }, [copilotOpen, copilotSeed]) // eslint-disable-line
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, busy])

  if (!copilotOpen) return null
  return (
    <div className="no-print fixed inset-2 top-[76px] md:inset-auto md:right-4 md:top-[96px] md:bottom-4 md:w-[440px] glass-strong flex flex-col shadow-2xl z-50 pop">
      <div className="flex items-center gap-2 p-3 border-b border-line">
        <Sparkles size={18} className="text-blue-300" />
        <div className="font-semibold">Ask your campus</div>
        <span className="chip ml-1">grounded in live twin data</span>
        <button className="btn !p-1.5 ml-auto" onClick={closeCopilot}><X size={16} /></button>
      </div>
      <div className="flex-1 overflow-auto p-3 space-y-3">
        {msgs.length === 0 && (
          <div className="space-y-2">
            <div className="text-sm text-slate-400">Answers come only from live tool calls on the twin, and every number is checked against the data.</div>
            {SUGGEST.map((s) => <button key={s} className="btn w-full !justify-start text-left !font-normal" onClick={() => ask(s)}>{s}</button>)}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : ''}>
            <div className={`rounded-xl px-3 py-2 text-sm leading-relaxed ${m.role === 'user' ? 'bg-blue-600/30 max-w-[85%]' : 'bg-black/30'}`}>
              {render(m.content)}
              {m.tools?.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {m.tools.map((t, j) => <span key={j} className="chip !text-[11px]"><Wrench size={11} />{t.name}</span>)}
                  {m.verified
                    ? <span className="chip !text-[11px] !bg-blue-500/20 !text-blue-200"><ShieldCheck size={11} /> numbers verified</span>
                    : <span className="chip !text-[11px] !bg-amber-500/20 !text-amber-200" title={`unverified: ${m.bad?.join(', ')}`}><ShieldAlert size={11} /> check numbers</span>}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={16} className="animate-spin" /> querying the twin…</div>}
        <div ref={end} />
      </div>
      <form className="p-3 border-t border-line flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim() && !busy) { ask(text); setText('') } }}>
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about energy, water, waste, rooms…" />
        <button className="btn btn-primary" disabled={busy}><Send size={16} /></button>
      </form>
    </div>
  )
}
