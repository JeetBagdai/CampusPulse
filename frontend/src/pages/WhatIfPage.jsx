import { useEffect, useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, inr, num } from '../api'
import { useStore } from '../store'

const TOGGLES = [
  ['led_retrofit', 'LED retrofit', 'Replace 36 W tube lights with 18 W LEDs'],
  ['fix_leaks', 'Leak alerts', 'Leaks fixed within 1 hour of a CampusPulse alert'],
  ['consolidate', 'Release underused bookings', 'Free up slots booked for classes that do not show up'],
]

function Stat({ label, value, sub, tone = '' }) {
  return (
    <div className="glass p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
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

  const chart = res && [
    { name: 'Energy (MWh)', Today: res.baseline.kwh / 1000, 'With policy': res.policy.kwh / 1000 },
    { name: 'Water (×10 kL)', Today: res.baseline.water_kl / 10, 'With policy': res.policy.water_kl / 10 },
    { name: 'CO₂ (t)', Today: res.baseline.co2_kg / 1000, 'With policy': res.policy.co2_kg / 1000 },
  ]

  return (
    <div className="p-3 md:p-4 grid grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)] gap-4">
      <div className="glass-panel p-4 h-fit">
        <h1 className="text-xl font-semibold">What-if simulator</h1>
        <p className="text-sm text-slate-400 mt-1">Replays 30 days of campus life with and without the policy, using the same random events, so the only difference is the policy.</p>
        <div className="mt-4">
          <div className="flex justify-between text-sm"><span>Auto-off when room empty</span>
            <span className="font-mono text-emerald-300">{policy.auto_off_minutes ? `${policy.auto_off_minutes} min` : 'off'}</span></div>
          <input type="range" min={0} max={60} step={5} value={policy.auto_off_minutes} className="w-full accent-emerald-500"
            onChange={(e) => setPolicy({ ...policy, auto_off_minutes: +e.target.value })} />
        </div>
        <div className="space-y-2 mt-3">
          {TOGGLES.map(([k, label, hint]) => (
            <label key={k} className="flex gap-3 items-start p-2 rounded-xl hover:bg-white/5 cursor-pointer">
              <input type="checkbox" className="mt-1 accent-emerald-500 w-4 h-4" checked={policy[k]} onChange={(e) => setPolicy({ ...policy, [k]: e.target.checked })} />
              <div><div className="font-medium text-sm">{label}</div><div className="text-xs text-slate-500">{hint}</div></div>
            </label>
          ))}
        </div>
        <button className="btn btn-primary w-full mt-4" disabled={!res}
          onClick={() => openCopilot(`Explain the what-if result for this policy and whether we should adopt it: ${JSON.stringify(policy)}`)}>
          <Sparkles size={16} /> Explain with AI</button>
      </div>

      <div className="space-y-4 min-w-0">
        {!res ? <div className="text-slate-400 flex items-center gap-2"><Loader2 className="animate-spin" size={16} /> simulating 30 days…</div> : (
          <>
            <div className={`grid grid-cols-2 xl:grid-cols-4 gap-3 ${busy ? 'opacity-60' : ''}`}>
              <Stat label="Saving per month" value={inr(res.monthly_saving_inr)} sub={`${inr(res.annual_saving_inr)} per year`} tone="text-emerald-300" />
              <Stat label="One-time cost" value={inr(res.capex_total_inr)} sub={res.opex_month_inr ? `+ ${inr(res.opex_month_inr)}/month running` : 'capex'} />
              <Stat label="Payback" value={res.payback_months == null ? '—' : res.payback_months === 0 ? 'instant' : `${res.payback_months} mo`} tone="text-sky-300" />
              <Stat label="CO₂ avoided / month" value={`${num(res.delta_per_month.co2_kg)} kg`} sub={`${num(res.delta_per_month.kwh)} kWh · ${num(res.delta_per_month.water_kl, 1)} kL`} tone="text-emerald-300" />
            </div>
            <div className="glass p-4">
              <div className="font-semibold mb-2">Today vs. with policy <span className="text-slate-500 font-normal text-sm">(30 days)</span></div>
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={chart} margin={{ left: -10 }}>
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: 'rgba(8,26,32,0.92)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10 }} formatter={(v) => num(v, 2)} />
                    <Legend />
                    <Bar isAnimationActive={false} dataKey="Today" fill="#f43f5e" radius={[6, 6, 0, 0]} />
                    <Bar isAnimationActive={false} dataKey="With policy" fill="#10b981" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="glass p-4 text-sm">
                <div className="font-semibold mb-2">Cost breakdown</div>
                {Object.entries(res.capex).map(([k, v]) => <div key={k} className="flex justify-between py-0.5"><span className="text-slate-400">{k}</span><span>{inr(v)}</span></div>)}
                {!Object.keys(res.capex).length && <div className="text-slate-500">No capital cost.</div>}
              </div>
              <div className="glass p-4 text-sm">
                <div className="font-semibold mb-2">Avoidable waste removed</div>
                <div className="flex justify-between py-0.5"><span className="text-slate-400">Energy in empty rooms</span><span>{num(res.baseline.waste_kwh)} → {num(res.policy.waste_kwh)} kWh</span></div>
                <div className="flex justify-between py-0.5"><span className="text-slate-400">Water lost to leaks</span><span>{num(res.baseline.leak_kl, 1)} → {num(res.policy.leak_kl, 1)} kL</span></div>
                <div className="text-xs text-slate-500 mt-2">Tariff ₹{res.assumptions.tariff_inr_per_kwh}/kWh · water ₹{res.assumptions.water_inr_per_kl}/kL · grid {res.assumptions.grid_ef} kg CO₂/kWh</div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
