import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Camera, CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { api } from '../api'

const STEPS = ['assigned', 'in_progress', 'resolved', 'verified']
const STEP_LABEL = { assigned: 'Assigned to staff', in_progress: 'Staff on it', resolved: 'Marked fixed', verified: 'Verified fixed' }

function Status({ ticket }) {
  const [s, setS] = useState(null)
  useEffect(() => {
    let alive = true
    const load = () => api.get(`/api/citizen-reports/${ticket}`).then((r) => alive && setS(r)).catch(() => {})
    load()
    const t = setInterval(load, 3000)
    return () => { alive = false; clearInterval(t) }
  }, [ticket])
  if (!s) return <div className="text-slate-400 text-center mt-6"><Loader2 className="animate-spin inline" /> loading…</div>
  const st = s.issue?.status
  const idx = st === 'auto_closed' || st === 'closed' ? 3 : STEPS.indexOf(st)
  return (
    <div className="glass p-4 mt-4">
      <div className="font-mono text-sky-300">{s.ticket}</div>
      <div className="font-semibold">{s.verdict?.description || 'Report received'}</div>
      {s.photo && <img src={s.photo} alt="" className="rounded-xl mt-3 max-h-56 w-full object-cover" />}
      {s.accepted === false ? <div className="text-amber-300 mt-3">Not raised: we couldn't confirm a problem in this photo.</div> : (
        <ol className="mt-4 space-y-2">
          {STEPS.map((k, i) => (
            <li key={k} className={`flex items-center gap-2 ${i <= idx ? 'text-blue-300' : 'text-slate-500'}`}>
              {i <= idx ? <CheckCircle2 size={18} /> : <span className="w-[18px] h-[18px] rounded-full border border-slate-600" />}
              {STEP_LABEL[k]}{i === idx && s.issue?.wo ? <span className="chip ml-1">{s.issue.wo}</span> : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

export default function ReportPage() {
  const [params] = useSearchParams()
  const [locs, setLocs] = useState([])
  const [loc, setLoc] = useState(params.get('loc') || '')
  const [note, setNote] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const ticket = params.get('ticket') || (res?.accepted ? res.ticket : null)
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])

  useEffect(() => { api.get('/api/locations').then(setLocs).catch(() => {}) }, [])

  const submit = async (e) => {
    e.preventDefault()
    if (!file || !loc) return
    setBusy(true); setErr('')
    const fd = new FormData()
    fd.append('photo', file)
    fd.append('loc', loc)
    fd.append('note', note)
    try { setRes(await api.form('/api/citizen-reports', fd)) } catch (e2) { setErr(e2.message) } finally { setBusy(false) }
  }
  const current = locs.find((l) => l.id === loc)

  return (
    <div className="min-h-full max-w-md mx-auto p-4">
      <div className="flex items-center gap-2 mb-4">
        <img src="/favicon.svg" className="w-9 h-9" alt="" />
        <div><div className="font-bold">CampusPulse</div><div className="text-xs text-slate-400">Report a problem on campus</div></div>
      </div>
      {params.get('ticket') ? <Status ticket={params.get('ticket')} /> : res ? (
        <>
          <div className={`glass p-4 ${res.accepted ? '' : 'border-amber-500/40'}`}>
            <div className="flex items-center gap-2 font-semibold">
              {res.accepted ? <CheckCircle2 className="text-emerald-400" /> : <XCircle className="text-amber-400" />}
              {res.accepted ? 'Thanks! Report accepted' : 'Not raised'}
            </div>
            <div className="text-sm text-slate-300 mt-1 whitespace-pre-wrap">{res.message}</div>
            <button className="btn mt-3 w-full" onClick={() => { setRes(null); setFile(null); setNote('') }}>Report another</button>
          </div>
          {ticket && <Status ticket={ticket} />}
        </>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <div className="glass p-3">
            <div className="text-xs text-slate-400 mb-1">Location</div>
            {current && params.get('loc') ? (
              <div><span className="font-mono text-sky-300">{current.id}</span> · {current.name}</div>
            ) : (
              <select className="input" value={loc} onChange={(e) => setLoc(e.target.value)} required>
                <option value="">Choose location…</option>
                {locs.map((l) => <option key={l.id} value={l.id}>{l.id} · {l.name}</option>)}
              </select>
            )}
          </div>
          <label className="glass p-4 flex flex-col items-center justify-center gap-2 cursor-pointer min-h-[200px]">
            {preview ? <img src={preview} alt="" className="rounded-xl max-h-72 object-contain" /> : (
              <><Camera size={36} className="text-blue-300" /><div className="font-semibold">Take a photo</div>
                <div className="text-xs text-slate-400 text-center">Leaking tap, overflowing bin, litter, or lights left on in an empty room</div></>
            )}
            <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
          <input className="input" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
          <button className="btn btn-primary w-full !py-3" disabled={!file || !loc || busy}>
            {busy ? <><Loader2 size={18} className="animate-spin" /> AI is checking your photo…</> : 'Submit report'}
          </button>
          {err && <div className="text-rose-300 text-sm">{err}</div>}
          <div className="text-xs text-slate-500 text-center">Faces are blurred automatically. No login needed.</div>
        </form>
      )}
    </div>
  )
}
