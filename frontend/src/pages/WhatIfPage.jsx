import { useEffect, useState } from 'react'
import { ChevronDown, Loader2, Sparkles } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, inr, num } from '../api'
import { useStore } from '../store'

const TOGGLES = [
  ['led_retrofit', 'LED retrofit', 'Replace 36 W tube lights with 18 W LEDs'],
  ['fix_leaks', 'Leak alerts', 'Leaks fixed within 1 hour of a CampusPulse alert'],
  ['consolidate', 'Release underused bookings', 'Free up slots booked for classes that do not show up'],
]
const AUTO_OFF = [0, 5, 10, 15, 30, 60]
const C = { today: '#f43f5e', policy: '#6ea0f5' }
const PART_COLORS = ['#6ea0f5', '#fbbf24', '#f87171', '#94a3b8']
const TIP = { background: 'rgba(30,30,30,0.95)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, fontSize: 12 }

const pct = (v, total) => (total > 0 ? Math.round((100 * v) / total) : 0)

function Big({ value, label, tone = '' }) {
  return (
    <div>
      <div className={`text-3xl md:text-4xl font-light tracking-tight tabular-nums ${tone}`}>{value}</div>
      <div className="text-sm text-slate-400 mt-1 leading-snug">{label}</div>
    </div>
  )
}

function Swatch({ color }) {
  return <span className="w-3 h-3 rounded-[3px] shrink-0" style={{ background: color }} />
}

function SectionTitle({ children, right }) {
  return (
    <div className="flex items-center mb-4">
      <h2 className="font-semibold text-[15px]">{children}</h2>
      {right && <div className="ml-auto text-xs text-slate-500">{right}</div>}
    </div>
  )
}

export default function WhatIfPage() {
  const openCopilot = useStore((s) => s.openCopilot)
  const [policy, setPolicy] = useState({ auto_off_minutes: 10, led_retrofit: true, fix_leaks: true, consolidate: false })
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let alive = true
    setBusy(true)
    const t = setTimeout(() => {
      api.post('/api/whatif', { ...policy, auto_off_minutes: policy.auto_off_minutes || null })
        .then((r) => alive && setRes(r)).finally(() => alive && setBusy(false))
    }, 250)
    return () => { alive = false; clearTimeout(t) }
  }, [policy])

  // where the monthly saving comes from
  const parts = res ? (() => {
    const { tariff_inr_per_kwh: t, water_inr_per_kl: w } = res.assumptions
    const d = res.delta_per_month
    const emptyKwh = Math.max(0, d.waste_kwh)
    const otherKwh = Math.max(0, d.kwh - d.waste_kwh)
    const waterKl = Math.max(0, d.water_kl)
    return [
      { label: 'Lights and fans off in empty rooms', amount: `${num(emptyKwh)} kWh`, inr: emptyKwh * t, note: 'auto-off' },
      { label: 'More efficient lighting', amount: `${num(otherKwh)} kWh`, inr: otherKwh * t, note: 'LED retrofit' },
      { label: 'Water no longer leaking', amount: `${num(waterKl, 1)} kL`, inr: waterKl * w, note: 'leak alerts' },
    ].map((p, i) => ({ ...p, color: PART_COLORS[i] }))
  })() : []
  const partsTotal = parts.reduce((a, p) => a + p.inr, 0)
  const capex = res ? Object.entries(res.capex).map(([name, v], i) => ({ name, v, color: PART_COLORS[i % PART_COLORS.length] })) : []
  const reduction = (a, b) => (a > 0 ? Math.round((100 * (a - b)) / a) : 0)

  return (
    <div className="p-3 md:p-6 max-w-[1280px] mx-auto">
      {/* page header */}
      <div className="flex items-start gap-3 mb-5">
        <div>
          <h1 className="text-2xl md:text-3xl font-light tracking-tight">What-if simulator</h1>
          <p className="text-sm text-slate-400 mt-1 max-w-[620px]">Replays 30 days of campus life with and without a policy, using the same random events, so the only difference is the policy.</p>
        </div>
        <button className="btn btn-primary ml-auto shrink-0" disabled={!res}
          onClick={() => openCopilot(`Explain the what-if result for this policy and whether we should adopt it: ${JSON.stringify(policy)}`)}>
          <Sparkles size={16} /><span className="hidden sm:inline">Explain with AI</span>
        </button>
      </div>

      <div className="glass-panel overflow-hidden">
        {/* policy bar */}
        <div className="flex flex-wrap items-center gap-2 px-4 md:px-6 py-3 border-b border-white/10">
          <span className="text-xs uppercase tracking-wider text-slate-500 mr-1">Policy</span>
          {TOGGLES.map(([k, label, hint]) => (
            <button key={k} title={hint} onClick={() => setPolicy({ ...policy, [k]: !policy[k] })}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition border
                ${policy[k] ? 'bg-blue-400/15 border-blue-300/40 text-blue-100' : 'border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}>
              {label}
            </button>
          ))}
          <label className="md:ml-auto flex items-center gap-2 text-sm text-slate-400">
            Auto-off after
            <span className="relative">
              <select className="input !w-auto !py-1 !pl-3 !pr-8 appearance-none text-slate-100" value={policy.auto_off_minutes}
                onChange={(e) => setPolicy({ ...policy, auto_off_minutes: +e.target.value })}>
                {AUTO_OFF.map((m) => <option key={m} value={m}>{m ? `${m} min empty` : 'never'}</option>)}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400" />
            </span>
          </label>
        </div>

        {!res ? (
          <div className="p-10 text-slate-400 flex items-center gap-2"><Loader2 className="animate-spin" size={16} /> Simulating 30 days…</div>
        ) : (
          <div className={`transition-opacity ${busy ? 'opacity-60' : ''}`}>
            {/* row 1: saving breakdown + one-time cost */}
            <div className="grid grid-cols-1 lg:grid-cols-2">
              <section className="p-4 md:p-6 lg:border-r border-white/10">
                <SectionTitle>Monthly saving</SectionTitle>
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl md:text-5xl font-light tracking-tight tabular-nums">{inr(res.monthly_saving_inr)}</span>
                  <span className="text-sm text-slate-400">per month</span>
                </div>
                <div className="flex h-2 rounded-full overflow-hidden mt-4 bg-white/5">
                  {parts.map((p) => <div key={p.label} style={{ width: `${pct(p.inr, partsTotal)}%`, background: p.color }} />)}
                </div>
                <div className="mt-4 divide-y divide-white/5">
                  {parts.map((p) => (
                    <div key={p.label} className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] md:grid-cols-[auto_minmax(0,1fr)_100px_90px_44px] items-center gap-x-3 py-2.5 text-sm">
                      <Swatch color={p.color} />
                      <div className="min-w-0"><div className="truncate">{p.label}</div><div className="text-[11px] text-slate-500">{p.note}</div></div>
                      <div className="text-slate-300 tabular-nums text-right max-md:hidden">{p.amount}</div>
                      <div className="tabular-nums text-right">{inr(p.inr)}</div>
                      <div className="text-slate-500 tabular-nums text-right text-xs max-md:hidden">{pct(p.inr, partsTotal)}%</div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="p-4 md:p-6 border-t lg:border-t-0 border-white/10">
                <SectionTitle right="one-time">Investment needed</SectionTitle>
                {capex.length ? (
                  <div className="flex flex-col sm:flex-row items-center gap-6">
                    <div className="relative w-44 h-44 shrink-0">
                      <ResponsiveContainer>
                        <PieChart>
                          <Pie data={capex} dataKey="v" nameKey="name" innerRadius="62%" outerRadius="100%" stroke="none" isAnimationActive={false}>
                            {capex.map((c) => <Cell key={c.name} fill={c.color} />)}
                          </Pie>
                          <Tooltip contentStyle={TIP} formatter={(v) => inr(v)} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                        <div className="text-lg font-light tabular-nums">{inr(res.capex_total_inr)}</div>
                        <div className="text-[11px] text-slate-500">total</div>
                      </div>
                    </div>
                    <div className="w-full space-y-3 text-sm">
                      {capex.map((c) => (
                        <div key={c.name} className="grid grid-cols-[auto_minmax(0,1fr)_auto_40px] items-center gap-x-3">
                          <Swatch color={c.color} />
                          <span className="truncate">{c.name}</span>
                          <span className="tabular-nums">{inr(c.v)}</span>
                          <span className="text-xs text-slate-500 tabular-nums text-right">{pct(c.v, res.capex_total_inr)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : <div className="text-sm text-slate-500">No capital cost for this policy.</div>}
                <div className="flex flex-wrap gap-2 mt-6">
                  <span className="chip !py-1 !px-3">Payback {res.payback_months == null ? 'n/a' : res.payback_months === 0 ? 'instant' : `${res.payback_months} months`}</span>
                  {res.opex_month_inr > 0 && <span className="chip !py-1 !px-3">+ {inr(res.opex_month_inr)}/month running cost</span>}
                </div>
              </section>
            </div>

            {/* row 2: daily bill, today vs with policy */}
            <section className="p-4 md:p-6 border-t border-white/10">
              <SectionTitle right={`${res.days} simulated days`}>Daily electricity and water bill</SectionTitle>
              <div className="flex flex-wrap gap-x-10 gap-y-3 mb-4">
                <Big value={inr(res.baseline.bill_inr)} label="today, 30 days" />
                <Big value={inr(res.policy.bill_inr)} label="with policy" tone="text-blue-200" />
              </div>
              <div className="h-64 md:h-72 -ml-2">
                <ResponsiveContainer>
                  <AreaChart data={res.daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <defs>
                      {Object.entries(C).map(([k, c]) => (
                        <linearGradient key={k} id={`wf-${k}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={c} stopOpacity={0.22} />
                          <stop offset="100%" stopColor={c} stopOpacity={0} />
                        </linearGradient>
                      ))}
                    </defs>
                    <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="date" tick={{ fill: '#8a8a8a', fontSize: 11 }} tickLine={false} axisLine={false} interval={4} />
                    <YAxis tick={{ fill: '#8a8a8a', fontSize: 11 }} tickLine={false} axisLine={false} width={56}
                      tickFormatter={(v) => `₹${num(v / 1000, 1)}k`} domain={['auto', 'auto']} />
                    <Tooltip contentStyle={TIP} formatter={(v) => inr(v)} />
                    <Area isAnimationActive={false} type="monotone" dataKey="today" name="Today" stroke={C.today} strokeWidth={2}
                      fill="url(#wf-today)" dot={{ r: 2.5, fill: C.today, strokeWidth: 0 }} />
                    <Area isAnimationActive={false} type="monotone" dataKey="policy" name="With policy" stroke={C.policy} strokeWidth={2}
                      fill="url(#wf-policy)" dot={{ r: 2.5, fill: C.policy, strokeWidth: 0 }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="flex gap-2 mt-3">
                <span className="chip !py-1 !px-3 !gap-2"><Swatch color={C.today} /> Today</span>
                <span className="chip !py-1 !px-3 !gap-2"><Swatch color={C.policy} /> With policy</span>
              </div>
            </section>

            {/* row 3: waste removed + other figures */}
            <div className="grid grid-cols-1 lg:grid-cols-2 border-t border-white/10">
              <section className="p-4 md:p-6 lg:border-r border-white/10">
                <SectionTitle>Avoidable waste removed</SectionTitle>
                <div className="grid grid-cols-2 gap-6">
                  <Big value={`${reduction(res.baseline.waste_kwh, res.policy.waste_kwh)}%`}
                    label={`less energy in empty rooms (${num(res.baseline.waste_kwh)} → ${num(res.policy.waste_kwh)} kWh)`} />
                  <Big value={`${reduction(res.baseline.leak_kl, res.policy.leak_kl)}%`}
                    label={`less water lost to leaks (${num(res.baseline.leak_kl, 1)} → ${num(res.policy.leak_kl, 1)} kL)`} />
                </div>
              </section>
              <section className="p-4 md:p-6 border-t lg:border-t-0 border-white/10">
                <SectionTitle>Over a year</SectionTitle>
                <div className="grid grid-cols-3 gap-4">
                  <Big value={inr(res.annual_saving_inr)} label="saved per year" />
                  <Big value={`${num((res.delta_per_month.co2_kg * 12) / 1000, 1)} t`} label="CO₂ avoided" />
                  <Big value={`${num((res.delta_per_month.kwh * 12) / 1000, 1)}`} label="MWh not used" />
                </div>
              </section>
            </div>

            <div className="px-4 md:px-6 py-3 border-t border-white/10 text-[11px] text-slate-500">
              Tariff ₹{res.assumptions.tariff_inr_per_kwh}/kWh · water ₹{res.assumptions.water_inr_per_kl}/kL · grid {res.assumptions.grid_ef} kg CO₂/kWh (CEA). Campus readings are simulated.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
