import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, Video, X } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import Twin3D from '../components/Twin3D'
import IssueCard from '../components/IssueCard'
import { api, hhmm, inr, num } from '../api'
import { OPEN_ISSUE, STATUS_COLOR, TYPE_META, issueTitle, useStore } from '../store'
import { TypeIcon } from '../components/Icons'

const LEGEND = [['active', 'occupied'], ['idle', 'empty / off'], ['energy', 'energy waste'], ['water', 'water leak'],
  ['waste', 'bin / litter'], ['underused', 'underused booking'], ['fixed', 'fixed']]
// issues / trends / activity side panel on the twin (hidden for now)
const SHOW_OVERVIEW = false
const FIX_LABEL = { tube_light: 'Tube lights', led_light: 'LED lights', fan: 'Fans', ac: 'AC', projector: 'Projector', pc: 'PCs', exhaust: 'Exhaust' }

function ReportQR({ id }) {
  const url = `${location.origin}/report?loc=${id}`
  return (
    <div className="flex items-center gap-3 mt-3 p-2 well">
      <div className="bg-white p-1.5 rounded-lg"><QRCodeSVG value={url} size={84} /></div>
      <div className="text-xs text-slate-400">
        <div className="font-semibold text-slate-200 mb-1">Student photo report</div>
        Scan to report a problem at <span className="font-mono text-sky-300">{id}</span>
        <div className="break-all mt-1 text-slate-500">{url}</div>
      </div>
    </div>
  )
}

function Drawer({ id }) {
  const { campus, snap, select } = useStore()
  const room = campus.rooms.find((r) => r.id === id)
  const bin = campus.bins.find((b) => b.id === id)
  const live = room ? snap.rooms[id] : snap.bins[id]
  const issues = snap.issues.filter((i) => i.target === id)
  const today = new Date(snap.clock).getDay()
  const dow = (today + 6) % 7
  const slots = room?.timetable?.filter((s) => s.day === dow) || []
  return (
    <div className="pop">
      <div className="flex items-start">
        <div>
          <div className="font-mono text-sky-300 text-sm">{id}</div>
          <div className="text-lg font-semibold">{room?.name || bin?.name}</div>
          <div className="text-sm text-slate-400">{room ? `${campus.buildings.find((b) => b.id === room.building)?.name}, floor ${room.floor}` : 'Bin with fill sensor'}</div>
        </div>
        <button className="ml-auto btn !p-1.5" onClick={() => select(null)}><X size={16} /></button>
      </div>
      {room && live && room.type !== 'washroom' && (
        <div className="grid grid-cols-3 gap-2 mt-3 text-center">
          <div className="well p-2"><div className="text-xs text-slate-400">People</div><div className="text-xl font-semibold">{live.occ}<span className="text-xs text-slate-500">/{room.capacity}</span></div></div>
          <div className="well p-2"><div className="text-xs text-slate-400">Power</div><div className="text-xl font-semibold">{num(live.power_w)}<span className="text-xs text-slate-500"> W</span></div></div>
          <div className="well p-2"><div className="text-xs text-slate-400">Wasted today</div><div className="text-xl font-semibold text-rose-300">{num(live.waste_kwh_today, 1)}<span className="text-xs text-slate-500"> kWh</span></div></div>
        </div>
      )}
      {room && live && room.type === 'washroom' && (
        <div className="mt-3 well p-2"><span className="text-xs text-slate-400">Water flow </span><span className="text-xl font-semibold">{live.flow_lpm}</span> L/min</div>
      )}
      {bin && live && (
        <div className="mt-3 well p-2">
          <div className="text-xs text-slate-400">Fill level</div>
          <div className="h-3 rounded-full bg-white/10 mt-1 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${live.fill}%`, background: live.fill >= 85 ? '#f43f5e' : live.fill >= 60 ? '#f59e0b' : '#10b981' }} /></div>
          <div className="text-sm mt-1">{live.fill}%{live.minutes_to_full ? ` · full in ~${live.minutes_to_full} min` : ''}</div>
        </div>
      )}
      {room && live?.on && (
        <div className="flex flex-wrap gap-1 mt-3">
          {room.fixtures.map((f) => (
            <span key={f.type} className={`chip ${live.on[f.type] ? '!bg-amber-400/20 !text-amber-200' : ''}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${live.on[f.type] ? 'bg-amber-300 shadow-[0_0_6px_#fcd34d]' : 'bg-slate-600'}`} />{FIX_LABEL[f.type]} ×{f.count}
            </span>
          ))}
          {live.cv_live && <span className="chip !bg-blue-500/20 !text-blue-200"><Video size={12} />live camera</span>}
        </div>
      )}
      {slots.length > 0 && (
        <div className="mt-3 text-sm">
          <div className="text-xs text-slate-400 mb-1">Timetable today</div>
          <div className="flex flex-wrap gap-1">{slots.map((s) => <span key={s.hour} className="chip">{s.hour}:00 {s.course}</span>)}</div>
        </div>
      )}
      <ReportQR id={id} />
      <div className="mt-3 space-y-2">{issues.slice(0, 3).map((i) => <IssueCard key={i.id} issue={i} />)}</div>
    </div>
  )
}

function scoreTone(s) {
  return s >= 85 ? 'text-emerald-300' : s >= 70 ? 'text-amber-300' : 'text-rose-300'
}

function Trends() {
  const { snap, campus } = useStore()
  const [daily, setDaily] = useState([])
  useEffect(() => {
    api.get('/api/history?hours=1').then((h) => setDaily(h.daily.slice(-14).map((d) => {
      const s = Object.values(d.b).reduce((a, v) => ({ kwh: a.kwh + v.kwh, waste: a.waste + v.waste_kwh }), { kwh: 0, waste: 0 })
      return { date: d.date.slice(5), used: Math.round(s.kwh - s.waste), wasted: Math.round(s.waste) }
    })))
  }, [])
  const k = snap.kpis
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        {[['Energy', num(k.kwh_today), 'kWh'], ['Water', num(k.water_l_today), 'L'], ['CO₂', num(k.co2_kg_today), 'kg']].map(([l, v, u]) => (
          <div key={l} className="well p-2.5">
            <div className="text-[11px] text-slate-400">{l} today</div>
            <div className="font-bold tabular-nums">{v} <span className="text-[11px] text-slate-500 font-normal">{u}</span></div>
          </div>
        ))}
      </div>
      <div className="well p-3">
        <div className="text-sm font-semibold mb-1">Energy, last 14 days <span className="text-slate-500 font-normal">(kWh)</span></div>
        <div className="h-36">
          <ResponsiveContainer>
            <AreaChart data={daily} margin={{ left: -18, right: 4, top: 4, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#64748b' }} interval={2} />
              <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
              <Tooltip contentStyle={{ background: 'rgba(8,26,32,0.92)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, fontSize: 12 }} />
              <Area isAnimationActive={false} type="monotone" dataKey="used" stackId="1" stroke="#8ab4f8" fill="#8ab4f855" name="useful" />
              <Area isAnimationActive={false} type="monotone" dataKey="wasted" stackId="1" stroke="#fb7185" fill="#fb718566" name="wasted (empty rooms)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="space-y-2">
        {campus.buildings.map((b) => {
          const s = snap.buildings[b.id]
          return (
            <div key={b.id} className="well p-2.5 flex items-center gap-3">
              <span className="w-2 h-2 rounded-full" style={{ background: b.color }} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold truncate">{b.name}</div>
                <div className="text-[11px] text-slate-400">energy efficiency {s.energy_eff}% · water {s.water_eff}%</div>
              </div>
              <div className={`text-xl font-bold ${scoreTone(s.score)}`}>{s.score}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Activity() {
  const snap = useStore((s) => s.snap)
  return (
    <div className="space-y-1.5 text-[13px]">
      {snap.events.map((e, n) => (
        <div key={n} className="flex gap-2"><span className="font-mono text-slate-500 shrink-0">{hhmm(e.t)}</span>
          <span className={e.kind === 'verified' ? 'text-emerald-300' : e.kind === 'detected' ? 'text-amber-200' : e.kind === 'escalated' ? 'text-rose-300' : 'text-slate-300'}>{e.text}</span></div>
      ))}
    </div>
  )
}

function Overview() {
  const snap = useStore((s) => s.snap)
  const [tab, setTab] = useState('issues')
  const active = snap.issues.filter((i) => !['verified', 'auto_closed', 'closed'].includes(i.status))
  const TABS = [['issues', `Issues${active.length ? ` (${active.length})` : ''}`], ['trends', 'Trends'], ['activity', 'Activity']]
  return (
    <div>
      <div className="flex gap-1 p-1 rounded-full bg-black/25 border border-white/5 mb-3">
        {TABS.map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex-1 py-1.5 rounded-full text-sm font-semibold transition ${tab === k ? 'bg-blue-400/15 text-blue-100 ring-1 ring-blue-300/30' : 'text-slate-400 hover:text-slate-200'}`}>{l}</button>
        ))}
      </div>
      {tab === 'issues' && (
        active.length === 0
          ? <div className="text-center text-slate-400 text-sm py-10">All clear. No open issues on campus.</div>
          : <div className="space-y-2">{active.slice(0, 8).map((i) => <IssueCard key={i.id} issue={i} compact />)}</div>
      )}
      {tab === 'trends' && <Trends />}
      {tab === 'activity' && <Activity />}
    </div>
  )
}

function KpiCard() {
  const k = useStore((s) => s.snap.kpis)
  const items = [
    ['Wasted', inr(k.wasted_inr_today), 'text-rose-300'],
    ['Open', k.open_issues, k.open_issues ? 'text-amber-300' : 'text-slate-100'],
    ['Saved', inr(k.saved_inr), 'text-emerald-300'],
    ['Score', `${k.score}`, scoreTone(k.score)],
  ]
  return (
    <div className="absolute left-3 top-[76px] md:left-4 md:top-[96px] glass grid grid-cols-4 divide-x divide-white/10 pointer-events-none max-md:right-3">
      {items.map(([l, v, tone]) => (
        <div key={l} className="px-2.5 py-2 md:px-4 md:py-2.5 min-w-0">
          <div className="text-[9px] md:text-[10px] uppercase tracking-wider text-slate-400 truncate">{l}</div>
          <div className={`text-base md:text-xl font-extrabold tabular-nums leading-tight ${tone}`}>{v}</div>
        </div>
      ))}
    </div>
  )
}

// A card slides in for each newly detected issue; clicking it flies the camera there.
const TOAST_MS = 7000
function AlertToasts() {
  const issues = useStore((s) => s.snap.issues)
  const wos = useStore((s) => s.snap.workorders)
  const tourOn = useStore((s) => s.tourOn)
  const select = useStore((s) => s.select)
  const seen = useRef(null)
  const [toasts, setToasts] = useState([])

  useEffect(() => {
    // issues already open when the page loads don't pop up
    if (seen.current === null) { seen.current = new Set(issues.map((i) => i.id)); return }
    const fresh = issues.filter((i) => OPEN_ISSUE(i) && !seen.current.has(i.id))
    if (!fresh.length) return
    fresh.forEach((i) => seen.current.add(i.id))
    setToasts((t) => [...fresh.map((i) => ({ id: i.id, at: Date.now() })), ...t].slice(0, 3))
  }, [issues])

  useEffect(() => {
    if (!toasts.length) return
    const t = setInterval(() => setToasts((ts) => ts.filter((x) => Date.now() - x.at < TOAST_MS)), 1000)
    return () => clearInterval(t)
  }, [toasts.length])

  if (tourOn || !toasts.length) return null
  const dismiss = (id) => setToasts((ts) => ts.filter((x) => x.id !== id))
  return (
    <div className="absolute z-20 flex flex-col gap-2 left-3 right-3 top-[140px] md:top-auto md:left-1/2 md:right-auto md:-translate-x-1/2 md:bottom-6 md:w-[420px]">
      {toasts.map(({ id }) => {
        const i = issues.find((x) => x.id === id)
        if (!i) return null
        const meta = TYPE_META[i.type] || {}
        const wo = wos?.[i.wo]
        return (
          <div key={id} className="glass-strong !rounded-2xl flex items-center gap-3 p-3 pop">
            <button onClick={() => { select(i.target); dismiss(id) }} className="flex items-center gap-3 flex-1 min-w-0 text-left">
              <span className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${meta.color}26`, color: meta.color }}>
                <TypeIcon type={i.type} size={17} />
              </span>
              <span className="min-w-0">
                <span className="block font-semibold text-sm truncate">{issueTitle(i)}</span>
                <span className="block text-xs text-slate-400 truncate">
                  {i.rate_inr_hr > 0 && <span className="text-rose-300">{inr(i.rate_inr_hr)}/h · </span>}
                  {wo ? `sent to ${wo.assignee}` : i.location}
                </span>
              </span>
            </button>
            <button className="btn !p-1.5 shrink-0" onClick={() => dismiss(id)} aria-label="Dismiss"><X size={14} /></button>
          </div>
        )
      })}
    </div>
  )
}

function AllClear() {
  const open = useStore((s) => s.snap.kpis.open_issues)
  if (open) return null
  return (
    <div className="absolute z-10 left-1/2 -translate-x-1/2 top-[140px] md:top-[96px] glass-strong !rounded-full px-4 py-2 flex items-center gap-2 text-sm whitespace-nowrap pointer-events-none pop">
      <CheckCircle2 size={16} className="text-emerald-300" />
      <span className="font-semibold">All clear</span>
      <span className="text-slate-400 max-sm:hidden">· the campus is running clean</span>
    </div>
  )
}

function Legend() {
  const [open, setOpen] = useState(false)
  return (
    <div className="absolute left-4 bottom-4 max-md:hidden">
      {open && (
        <div className="glass px-3 py-2 mb-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs pop">
          {LEGEND.map(([k, label]) => (
            <span key={k} className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: STATUS_COLOR[k] }} />{label}</span>
          ))}
        </div>
      )}
      <button className="btn !py-1 !px-3 text-xs" onClick={() => setOpen(!open)}>{open ? 'Hide legend' : 'Legend'}</button>
    </div>
  )
}

export default function TwinPage() {
  const selected = useStore((s) => s.selected)
  return (
    <div className="h-full relative min-h-[520px]">
      <Twin3D />
      <KpiCard />
      <AllClear />
      <AlertToasts />
      <Legend />
      {/* details panel for the selected room/bin; the issues overview is hidden while SHOW_OVERVIEW is false.
          desktop: floating side panel; phone: bottom sheet over the lower part of the map */}
      {(selected || SHOW_OVERVIEW) && <aside className="glass-panel absolute z-10 p-3 overflow-auto
        md:right-3 md:top-[96px] md:bottom-[88px] md:w-[380px]
        max-md:inset-x-2 max-md:bottom-[150px] max-md:h-[40%] max-md:!rounded-b-2xl max-md:!rounded-t-3xl">
        <div className="md:hidden mx-auto mb-2 h-1 w-10 rounded-full bg-white/25" />
        {selected ? <Drawer id={selected} /> : <Overview />}
      </aside>}
    </div>
  )
}
