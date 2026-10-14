import { useState } from 'react'
import { Droplets, CalendarX, Lightbulb, Pause, Play, RotateCcw, Trash2, X } from 'lucide-react'
import { api } from '../api'
import { useStore } from '../store'

export default function DemoPanel() {
  const { demoOpen, toggleDemo, campus, snap } = useStore()
  const rooms = campus?.rooms.filter((r) => r.type !== 'washroom') || []
  const washrooms = campus?.rooms.filter((r) => r.type === 'washroom') || []
  const [room, setRoom] = useState(null)
  const [wash, setWash] = useState(null)
  const [bin, setBin] = useState(null)
  const [msg, setMsg] = useState('')
  if (!demoOpen || !campus || !snap) return null
  const roomId = room || campus.live_room || rooms[0].id
  const washId = wash || washrooms[0].id
  const binId = bin || campus.bins[0].id

  const run = async (fn, label) => {
    try { await fn(); setMsg(`Done: ${label}`) } catch (e) { setMsg(`Failed: ${e.message}`) }
  }
  const inject = (scenario, target) => run(() => api.post('/api/demo/inject', { scenario, target }), `${scenario} → ${target}`)
  const sel = (value, set, list) => (
    <select className="input !py-1 !w-auto text-sm min-w-0 flex-1" value={value} onChange={(e) => set(e.target.value)}>
      {list.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.name}</option>)}
    </select>
  )

  return (
    <div className="no-print fixed inset-x-2 bottom-[76px] md:inset-x-auto md:left-4 md:bottom-4 md:w-[460px] max-h-[80vh] overflow-auto glass-strong p-4 shadow-2xl z-50 pop">
      <div className="flex items-center mb-3">
        <div className="font-semibold">Demo controls</div>
        <span className="chip ml-2">Ctrl+D</span>
        <button className="btn !p-1.5 ml-auto" onClick={toggleDemo}><X size={16} /></button>
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap gap-2 items-center">{sel(roomId, setRoom, rooms)}
          <button className="btn" onClick={() => inject('lights_left_on', roomId)}><Lightbulb size={15} /> Lights left on</button>
          <button className="btn" onClick={() => inject('underused_class', roomId)}><CalendarX size={15} /></button>
        </div>
        <div className="flex flex-wrap gap-2 items-center">{sel(washId, setWash, washrooms)}
          <button className="btn" onClick={() => inject('leak', washId)}><Droplets size={15} /> Leak</button>
        </div>
        <div className="flex flex-wrap gap-2 items-center">{sel(binId, setBin, campus.bins)}
          <button className="btn" onClick={() => inject('bin_spike', binId)}><Trash2 size={15} /> Bin spike</button>
        </div>
      </div>
      <div className="border-t border-line my-3" />
      <div className="flex gap-1 items-center flex-wrap">
        <span className="text-sm text-slate-400 mr-1">Speed</span>
        {[1, 5, 15, 60].map((x) => (
          <button key={x} className={`btn !py-1 ${snap.speed === x ? '!bg-emerald-500/25' : ''}`}
            onClick={() => run(() => api.post(`/api/demo/speed?x=${x}`), `speed ${x}×`)}>{x}×</button>
        ))}
        <button className="btn !py-1" onClick={() => run(() => api.post(`/api/demo/speed?x=${snap.speed}&paused=${!snap.paused}`), snap.paused ? 'resumed' : 'paused')}>
          {snap.paused ? <Play size={14} /> : <Pause size={14} />}</button>
      </div>
      <div className="flex gap-1 items-center flex-wrap mt-2">
        <span className="text-sm text-slate-400 mr-1">Jump to</span>
        {[[2, '2 AM'], [8, '8 AM'], [13, '1 PM'], [21, '9 PM']].map(([h, l]) => (
          <button key={h} className="btn !py-1" onClick={() => run(() => api.post(`/api/demo/jump?hour=${h}`), `jumped to ${l}`)}>{l}</button>
        ))}
      </div>
      <div className="flex gap-1 items-center flex-wrap mt-2">
        <span className="text-sm text-slate-400 mr-1">Real WhatsApp</span>
        {['demo', 'all', 'off'].map((m) => (
          <button key={m} className={`btn !py-1 ${snap.wa_mode === m ? '!bg-emerald-500/25' : ''}`}
            onClick={() => run(() => api.post(`/api/demo/wa-mode?mode=${m}`), `WhatsApp mode ${m}`)}>{m}</button>
        ))}
        <button className="btn btn-danger !py-1 ml-auto" onClick={() => confirm('Reset the simulation?') && run(() => api.post('/api/demo/reset'), 'reset')}>
          <RotateCcw size={14} /> Reset</button>
      </div>
      <div className="text-xs text-slate-500 mt-2">
        “demo” sends real WhatsApp only for injected, camera and photo-report issues. Channel: {snap.channel}. {msg}
      </div>
    </div>
  )
}
