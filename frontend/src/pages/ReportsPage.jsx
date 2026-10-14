import { useEffect, useState } from 'react'
import { FileText, Loader2, Printer, RefreshCw } from 'lucide-react'
import { api, inr, num } from '../api'

function Row({ k, v }) {
  return <tr className="border-b border-slate-200"><td className="py-1 pr-4 text-slate-500">{k}</td><td className="py-1 font-medium">{v}</td></tr>
}

function Doc({ r }) {
  const f = r.facts
  const s = r.sections
  const title = r.kind === 'naac' ? 'Green Audit: NAAC Criterion 7.1 (Environment)' : 'Weekly Sustainability Report'
  return (
    <div className="print-page bg-white/95 backdrop-blur-xl ring-1 ring-white/40 text-slate-900 rounded-3xl shadow-2xl max-w-[860px] mx-auto p-5 md:p-10 my-4">
      <div className="flex items-start border-b-2 border-emerald-600 pb-4 mb-6">
        <div>
          <div className="text-xs uppercase tracking-widest text-emerald-700 font-semibold">CampusPulse · continuous audit</div>
          <h1 className="text-2xl font-bold mt-1">{title}</h1>
          <div className="text-sm text-slate-500">{f.campus} · {f.period.from} to {f.period.to} ({f.period.days} days)</div>
        </div>
        <div className="ml-auto text-right text-xs text-slate-500">Generated {r.generated_at.slice(0, 16).replace('T', ' ')}</div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {[['Energy', `${num(f.energy.total_kwh)} kWh`, inr(f.energy.bill_inr)], ['Avoidable energy', `${num(f.energy.waste_kwh)} kWh`, `${f.energy.waste_share_pct}% · ${inr(f.energy.waste_inr)}`],
          ['Water', `${num(f.water.total_kl, 1)} kL`, `${num(f.water.leak_kl, 1)} kL leaked`], ['Carbon', `${num(f.energy.co2_kg)} kg CO₂`, `${num(f.energy.avoidable_co2_kg)} kg avoidable`]].map(([a, b, c]) => (
          <div key={a} className="rounded-xl bg-slate-100 p-3"><div className="text-xs text-slate-500">{a}</div><div className="text-lg font-bold">{b}</div><div className="text-xs text-slate-500">{c}</div></div>
        ))}
      </div>

      {r.kind === 'naac' ? (
        <>
          <h2 className="font-semibold text-lg mb-1">Summary</h2>
          <p className="mb-5 leading-relaxed">{s.summary}</p>
          {r.naac_sections.map(([code, name]) => (
            <div key={code} className="mb-5">
              <h2 className="font-semibold text-lg">{code} · {name}</h2>
              <p className="leading-relaxed mt-1">{s[code]}</p>
            </div>
          ))}
        </>
      ) : (
        <>
          <h2 className="font-semibold text-lg mb-1">Executive summary</h2>
          <p className="mb-5 leading-relaxed">{s.executive_summary}</p>
          {[['highlights', 'Highlights'], ['concerns', 'Concerns'], ['actions', 'Recommended actions']].map(([k, label]) => (
            <div key={k} className="mb-4">
              <h2 className="font-semibold text-lg">{label}</h2>
              <ul className="list-disc ml-6 mt-1 space-y-1">{(s[k] || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
          ))}
        </>
      )}

      <h2 className="font-semibold text-lg mt-6 mb-2">Building-wise data</h2>
      <div className="overflow-x-auto mb-6"><table className="w-full text-sm min-w-[520px]">
        <thead><tr className="text-left text-slate-500 border-b-2 border-slate-300"><th className="py-1">Building</th><th>Energy kWh</th><th>Avoidable kWh</th><th>Share</th><th>Water kL</th><th>Leaks kL</th></tr></thead>
        <tbody>{Object.values(f.buildings).map((b) => (
          <tr key={b.name} className="border-b border-slate-200"><td className="py-1">{b.name}</td><td>{num(b.energy_kwh)}</td><td>{num(b.waste_kwh)}</td><td>{b.waste_share_pct}%</td><td>{b.water_kl}</td><td>{b.leak_kl}</td></tr>
        ))}</tbody>
      </table></div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
        <div>
          <h2 className="font-semibold text-lg mb-2">Top avoidable-energy rooms</h2>
          <table className="w-full"><tbody>{f.top_waste_rooms.map((t) => <Row key={t.room} k={`${t.room} · ${t.name}`} v={`${num(t.waste_kwh)} kWh`} />)}</tbody></table>
        </div>
        <div>
          <h2 className="font-semibold text-lg mb-2">Action & recommendation</h2>
          <table className="w-full"><tbody>
            <Row k="Issues detected (session)" v={f.campuspulse_session.issues_detected} />
            <Row k="Fixed & verified" v={f.campuspulse_session.issues_verified_fixed} />
            <Row k="Saved by verified fixes" v={inr(f.campuspulse_session.saved_inr)} />
            <Row k="Recommended policy" v={f.recommendation.policy} />
            <Row k="Saving / month" v={inr(f.recommendation.monthly_saving_inr)} />
            <Row k="Payback" v={`${f.recommendation.payback_months} months`} />
          </tbody></table>
        </div>
      </div>

      <div className="text-[11px] text-slate-500 mt-8 border-t border-slate-200 pt-3">
        Emission factor {f.constants.grid_ef_kg_per_kwh} kg CO₂/kWh ({f.constants.grid_ef_source}). Tariff ₹{f.constants.tariff_inr_per_kwh}/kWh ({f.constants.tariff_source}).
        Water ₹{f.constants.water_inr_per_kl}/kL ({f.constants.water_source}). Every figure is computed by the CampusPulse engine; AI-written text is checked so it cannot introduce numbers absent from the data.
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const [kind, setKind] = useState('naac')
  const [reports, setReports] = useState({})
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState('')
  const r = reports[kind]

  const load = async (k, fresh = false) => {
    setBusy(k); setErr('')
    try {
      const data = fresh ? await api.post(`/api/reports/${k}`) : await api.get(`/api/reports/${k}`)
      setReports((prev) => ({ ...prev, [k]: data }))
    } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  useEffect(() => { if (!reports[kind]) load(kind) }, [kind]) // eslint-disable-line

  return (
    <div className="p-3 md:p-4">
      <div className="no-print glass-panel flex items-center gap-2 flex-wrap p-2 max-w-[860px] mx-auto">
        <div className="flex gap-1 p-1 rounded-full bg-black/25 border border-white/5">
          {[['naac', 'NAAC green audit (30 days)'], ['weekly', 'Weekly report']].map(([k, l]) => (
            <button key={k} onClick={() => setKind(k)}
              className={`px-4 py-1.5 rounded-full text-sm font-semibold transition ${kind === k ? 'bg-teal-400/15 text-teal-100 ring-1 ring-teal-300/30' : 'text-slate-400 hover:text-slate-200'}`}>
              <FileText size={14} className="inline -mt-0.5 mr-1.5" />{l}</button>
          ))}
        </div>
        <div className="ml-auto flex gap-2">
          <button className="btn !py-1.5" disabled={!!busy} onClick={() => load(kind, true)}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />} Regenerate</button>
          <button className="btn btn-primary !py-1.5" disabled={!r} onClick={() => window.print()}><Printer size={15} /> Print / PDF</button>
        </div>
      </div>
      {err && <div className="text-rose-300 mt-3 text-center">{err}</div>}
      {!r && busy && (
        <div className="print-page bg-white/90 rounded-3xl max-w-[860px] mx-auto p-5 md:p-10 my-4 space-y-4 animate-pulse">
          <div className="text-slate-500 text-sm flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Writing the report from live campus data…</div>
          {[70, 40, 95, 90, 60, 85, 92, 55].map((w, i) => <div key={i} className="h-3 rounded bg-slate-300" style={{ width: `${w}%` }} />)}
        </div>
      )}
      {r && <Doc r={r} />}
    </div>
  )
}
