import { useEffect, useRef, useState } from 'react'
import { CheckCheck, MessageCircle, Send } from 'lucide-react'
import { RoleIcon } from './Icons'
import TelegramIcon from './TelegramIcon'
import { api } from '../api'
import { useStore } from '../store'

const ROLES = [['electrician', 'Electrical'], ['plumber', 'Water'], ['housekeeping', 'Waste'], ['estate_manager', 'Estate']]
const ROLE_NAME = Object.fromEntries(ROLES)

export default function PhonePanel() {
  const snap = useStore((s) => s.snap)
  const [role, setRole] = useState('electrician')
  const [text, setText] = useState('')
  const end = useRef(null)
  const feed = snap.feed.filter((m) => role === 'all' || m.role === role)
  const real = snap.channel !== 'console'
  const app = ['telegram', 'console'].includes(snap.channel) ? 'Telegram' : 'WhatsApp'

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [feed.length])

  const send = async (body) => {
    await api.post('/api/wa/simulate', { role: role === 'all' ? 'electrician' : role, ...body })
  }

  return (
    <aside className="no-print glass-strong fixed inset-x-2 top-[76px] bottom-[148px] md:inset-auto md:left-4 md:top-[96px] md:bottom-[88px] md:w-[360px] z-40 flex flex-col p-3 pop">
      <div className="flex items-center gap-2 mb-2">
        {app === 'Telegram' ? <TelegramIcon size={32} />
          : <div className="w-8 h-8 rounded-full flex items-center justify-center bg-blue-500"><MessageCircle size={16} className="text-white" /></div>}
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm leading-tight truncate">Staff {app}{snap.bot?.username ? ` · @${snap.bot.username}` : ''}</div>
          <div className="text-[11px] text-slate-400 leading-tight">
            {real ? `live · linked: ${snap.bot?.linked?.length ? snap.bot.linked.join(', ') : 'nobody yet'}` : 'in-app preview (no messaging channel configured)'}
          </div>
        </div>
      </div>
      {snap.channel === 'telegram' && snap.bot?.username && (
        <a href={`https://t.me/${snap.bot.username}?start=judge`} target="_blank" rel="noreferrer"
          className="well px-2.5 py-1.5 mb-2 text-[11px] text-slate-300 hover:text-blue-100 block">
          Get these work orders on your phone: <span className="text-blue-200 underline">t.me/{snap.bot.username}?start=judge</span>
        </a>
      )}
      <div className="flex gap-1 flex-wrap mb-2">
        {[...ROLES, ['all', 'All']].map(([k, l]) => (
          <button key={k} onClick={() => setRole(k)} className={`chip ${role === k ? '!bg-blue-500/25 !text-blue-200' : ''}`}>{l}</button>
        ))}
      </div>
      <div className="flex-1 overflow-auto rounded-2xl p-2 space-y-2" style={{ background: 'rgba(0,0,0,0.22)', border: '1px solid rgba(255,255,255,0.06)' }}>
        {feed.length === 0 && <div className="text-xs text-slate-500 text-center mt-8">No messages yet. Work orders appear here as they are dispatched.</div>}
        {feed.map((m) => (
          <div key={m.id} className={`flex ${m.dir === 'in' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[88%] rounded-xl px-2.5 py-1.5 text-[13px] whitespace-pre-wrap leading-snug pop
              ${m.dir === 'in' ? 'bg-blue-500/30 text-white border border-blue-300/20' : 'bg-white/[0.07] text-slate-100 border border-white/10'}`}>
              {role === 'all' && <div className="text-[10px] text-blue-300 mb-0.5">{m.dir === 'in' ? 'from' : 'to'} {ROLE_NAME[m.role] || m.role}</div>}
              {m.text}
              {m.dir === 'out' && m.buttons?.length > 0 && m.wo && (
                <div className="flex gap-1 mt-1.5">
                  {m.buttons.map((b) => (
                    <button key={b} onClick={() => send({ text: b, button_id: `${b.toUpperCase().includes('DONE') ? 'DONE' : 'ACK'}:${m.wo}`, role: m.role })}
                      className="flex-1 rounded-lg bg-white/10 hover:bg-white/20 py-1 text-[12px] text-sky-300">{b}</button>
                  ))}
                </div>
              )}
              <div className="text-[10px] text-slate-400 text-right mt-0.5">
                {m.channel === 'console' ? 'in-app' : <><CheckCheck size={11} className="inline -mt-0.5 mr-0.5 text-blue-300" />{m.channel === 'telegram' ? 'Telegram' : 'WhatsApp'}</>}{m.status && !['ok', 'shown in app', 'delivered'].includes(m.status) ? ` · ${m.status}` : ''}
              </div>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
      <form className="flex gap-2 mt-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send({ text }); setText('') } }}>
        <input className="input !py-1.5 text-sm" value={text} onChange={(e) => setText(e.target.value)}
          placeholder={`Reply as ${ROLE_NAME[role] || 'Electrician'} (e.g. DONE WO-3)`} />
        <button className="btn btn-primary !px-2.5"><Send size={15} /></button>
      </form>
    </aside>
  )
}
