import { useEffect, useRef, useState } from 'react'
import { Camera, CameraOff, ImagePlus, Lightbulb, LightbulbOff } from 'lucide-react'
import { api, inr } from '../api'
import { STATUS_COLOR, TYPE_META, useStore } from '../store'
import { TypeIcon } from '../components/Icons'

const CAM = 'cam-live'
const SAMPLE_CAM = 'cam-sample'
const SAMPLES = [['empty', 'Empty'], ['half', 'Half full'], ['overflow', 'Overflowing']]
const STATUS_TEXT = { energy: 'Energy waste detected', water: 'Water leak detected', waste: 'Bin needs emptying',
  underused: 'Underused booking', litter: 'Litter reported', fixed: 'Fixed and verified', active: 'Occupied', idle: 'Empty, all off' }

function Stat({ label, value, sub }) {
  return (
    <div className="well p-2.5">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  )
}

function TwinStatus({ target }) {
  const { campus, snap } = useStore()
  const room = campus.rooms.find((r) => r.id === target)
  const bin = campus.bins.find((b) => b.id === target)
  const live = room ? snap.rooms[target] : snap.bins[target]
  const issue = snap.issues.find((i) => i.target === target && !['verified', 'auto_closed', 'closed'].includes(i.status))
  const status = live?.status || 'idle'
  return (
    <div className="glass p-3">
      <div className="text-xs text-slate-400 mb-1">On the twin</div>
      <div className="font-semibold">{target} · {room?.name || bin?.name}</div>
      <div className="flex items-center gap-2 mt-2 text-sm">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: STATUS_COLOR[status], boxShadow: `0 0 8px ${STATUS_COLOR[status]}` }} />
        {STATUS_TEXT[status] || status}
      </div>
      {issue && (
        <div className="well p-2 mt-2 text-sm flex items-center gap-2">
          <TypeIcon type={issue.type} size={14} />
          <span className="font-mono text-blue-200">{issue.id}</span>
          <span className="text-slate-300">{TYPE_META[issue.type].label}</span>
          {issue.rate_inr_hr > 0 && <span className="ml-auto text-rose-300">{inr(issue.rate_inr_hr)}/h</span>}
        </div>
      )}
    </div>
  )
}

export default function CamerasPage() {
  const { campus, snap } = useStore()
  const video = useRef(null)
  const canvas = useRef(null)
  const stream = useRef(null)
  const timer = useRef(null)
  const inflight = useRef(false)
  const [on, setOn] = useState(false)
  const [det, setDet] = useState(null)
  const [err, setErr] = useState('')
  const [calib, setCalib] = useState(null)
  const [mode, setMode] = useState('live') // live | sample
  const [busy, setBusy] = useState(false)
  const sampleBin = (campus.bins.find((b) => b.kind === 'food') || campus.bins[0]).id
  const liveTarget = snap.cv.bindings[CAM]
  const target = mode === 'sample' ? sampleBin : liveTarget
  const isWash = campus.rooms.find((r) => r.id === target)?.type === 'washroom'
  const isBin = campus.bins.some((b) => b.id === target)

  const stop = () => {
    clearInterval(timer.current)
    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null
    setOn(false)
  }
  useEffect(() => stop, [])
  useEffect(() => { api.get(`/api/cv/calibration?cam_id=${CAM}`).then(setCalib).catch(() => {}) }, [])

  const capture = () => {
    if (inflight.current || !video.current?.videoWidth) return
    const c = canvas.current
    c.width = 640
    c.height = Math.round(640 * video.current.videoHeight / video.current.videoWidth)
    c.getContext('2d').drawImage(video.current, 0, 0, c.width, c.height)
    inflight.current = true
    c.toBlob(async (blob) => {
      const fd = new FormData()
      fd.append('file', blob, 'frame.jpg')
      fd.append('cam_id', CAM)
      try { setDet(await api.form('/api/cv/frame', fd)) } catch (e) { setErr(e.message) } finally { inflight.current = false }
    }, 'image/jpeg', 0.75)
  }

  // send one still image (sample or upload) through the same server-side CV pipeline
  const analyseImage = async (blob, camId) => {
    setBusy(true); setErr('')
    try {
      const fd = new FormData()
      fd.append('file', blob, 'photo.jpg')
      fd.append('cam_id', camId)
      setDet(await api.form('/api/cv/frame', fd))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const runSample = async (name) => {
    stop(); setMode('sample')
    await api.post('/api/cv/bind', { cam_id: SAMPLE_CAM, target: sampleBin })
    const blob = await (await fetch(`/samples/bin-${name}.jpg`)).blob()
    await analyseImage(blob, SAMPLE_CAM)
  }
  const upload = async (file) => {
    if (!file) return
    stop(); setMode('live')
    await analyseImage(file, CAM)
  }

  const start = async () => {
    setErr(''); setMode('live'); setDet(null)
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
      video.current.srcObject = stream.current
      await video.current.play()
      setOn(true)
      timer.current = setInterval(capture, 500)
    } catch (e) {
      setErr(`Camera unavailable: ${e.message}`)
    }
  }

  const calibrate = async (state) => {
    try {
      await api.post(`/api/cv/calibrate?cam_id=${CAM}&state=${state}`)
      setCalib(await api.get(`/api/cv/calibration?cam_id=${CAM}`))
      setErr('')
    } catch (e) { setErr(e.message) }
  }
  const bind = (t) => api.post('/api/cv/bind', { cam_id: CAM, target: t })

  const targets = [...campus.rooms.map((r) => ({ id: r.id, name: r.name })), ...campus.bins.map((b) => ({ id: b.id, name: b.name }))]
  const binView = mode === 'sample' || isBin
  const waste = det && (binView ? det.bin_state === 'overflow' : det.people === 0 && (det.lights_on || det.fans_on))
  const verdict = !det ? null : binView
    ? (det.bin_state === 'overflow' ? 'Overflowing bin: pickup requested' : det.bin_state ? `Bin is ${det.bin_state}` : 'No bin found')
    : waste ? 'Empty room with power on' : det.people > 0 ? 'Occupied' : 'Empty, all off'

  return (
    <div className="p-3 md:p-4 max-w-[1300px] mx-auto">
      <div className="glass-panel p-4">
        <div className="flex items-center gap-2 flex-wrap mb-4">
          <h1 className="text-lg font-semibold mr-1">{mode === 'sample' ? 'Sample photo' : 'Live camera'}</h1>
          <span className="chip !bg-rose-500/20 !text-rose-200">
            <span className={`w-2 h-2 rounded-full ${on ? 'bg-rose-400 animate-pulse' : 'bg-slate-500'}`} />{on ? 'LIVE' : 'off'}
          </span>
          <span className="text-sm text-slate-400 ml-2">watches</span>
          <select className="input !py-1 !w-auto text-sm" value={target} disabled={mode === 'sample'} onChange={(e) => bind(e.target.value)}>
            {targets.map((t) => <option key={t.id} value={t.id}>{t.id} · {t.name}</option>)}
          </select>
          <div className="ml-auto">
            {on ? <button className="btn" onClick={stop}><CameraOff size={15} /> Stop</button>
              : <button className="btn btn-primary" onClick={start}><Camera size={15} /> Start camera</button>}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-4">
          <div className="space-y-3 min-w-0">
          <div className="relative rounded-2xl overflow-hidden bg-black/60 ring-1 ring-white/10 aspect-[4/3]">
            <video ref={video} className="hidden" muted playsInline />
            <canvas ref={canvas} className="hidden" />
            {det?.annotated ? <img src={det.annotated} className={`w-full h-full object-contain ${busy ? 'opacity-50' : ''}`} alt="annotated camera feed" draggable={false} />
              : <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm p-8 text-center">
                {busy ? 'Analysing…' : 'Start the camera, or try a sample photo below. Images are analysed on the server with YOLO; faces are blurred and nothing is stored.'}</div>}
          </div>

          <div className="glass p-3">
            <div className="text-sm font-semibold">No webcam? Try the trained bin model</div>
            <div className="text-xs text-slate-400 mb-2">YOLO11n fine-tuned on bin photos (90% of held-out photos correct). An overflowing bin raises a real issue on the twin.</div>
            <div className="flex gap-2 flex-wrap">
              {SAMPLES.map(([k, label]) => (
                <button key={k} disabled={busy} onClick={() => runSample(k)}
                  className="group relative w-24 h-20 rounded-xl overflow-hidden ring-1 ring-white/15 hover:ring-blue-300/60 transition">
                  <img src={`/samples/bin-${k}.jpg`} alt={label} className="w-full h-full object-cover group-hover:scale-105 transition" />
                  <span className="absolute inset-x-0 bottom-0 bg-black/60 text-[11px] font-semibold py-0.5">{label}</span>
                </button>
              ))}
              <label className="btn !h-20 !w-28 flex-col !gap-1 text-xs cursor-pointer">
                <ImagePlus size={18} /> Upload a photo
                <input type="file" accept="image/*" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
              </label>
            </div>
            <div className="text-[10px] text-slate-500 mt-2">Sample photos: Garbage_Fill_Level, Roboflow Universe (CC BY 4.0). Uploads are analysed for the room or bin selected above.</div>
          </div>
          </div>

          <div className="space-y-3 text-sm">
            {det ? (
              <>
                <div className={`rounded-2xl p-3 font-semibold ${waste ? 'bg-rose-500/20 text-rose-100 ring-1 ring-rose-300/30' : 'bg-emerald-500/15 text-emerald-100 ring-1 ring-emerald-300/20'}`}>{verdict}</div>
                <div className="grid grid-cols-2 gap-2">
                  {binView ? (
                    <Stat label="Bin (trained model)" value={det.bin_state || 'none'} sub={det.bin_state ? `confidence ${Math.round(det.bin_conf * 100)}%` : ''} />
                  ) : (
                    <>
                      <Stat label="People" value={det.people} />
                      <Stat label="Lights" value={det.lights_on ? 'ON' : 'OFF'} sub={`brightness ${det.brightness} / ${det.light_threshold}`} />
                      <Stat label="Fan" value={det.fans_on == null ? '…' : det.fans_on ? 'Spinning' : 'Still'} />
                      {isWash && <Stat label="Tap" value={det.tap_on == null ? '…' : det.tap_on ? 'Running' : 'Off'} />}
                    </>
                  )}
                </div>
              </>
            ) : <div className="text-slate-500">No detections yet.</div>}
            <TwinStatus target={target} />
            <details className="glass p-3">
              <summary className="text-xs text-slate-400 cursor-pointer select-none">Advanced: calibrate light detection</summary>
              <div className="flex items-center my-2">
                <div className="text-xs text-slate-400">For the room in front of the camera</div>
                <span className={`chip ml-auto !text-[11px] ${calib?.calibrated ? '!bg-blue-500/20 !text-blue-200' : ''}`}>
                  {calib?.calibrated ? `saved · on ${Math.round(calib.calib.on)} / off ${Math.round(calib.calib.off)}` : calib?.calib?.on || calib?.calib?.off ? 'half done' : 'not calibrated'}
                </span>
              </div>
              <div className="flex gap-2">
                <button className="btn !py-1 flex-1" disabled={!det} onClick={() => calibrate('on')}><Lightbulb size={14} /> Lights ON</button>
                <button className="btn !py-1 flex-1" disabled={!det} onClick={() => calibrate('off')}><LightbulbOff size={14} /> Lights OFF</button>
              </div>
            </details>
            {err && <div className="text-rose-300 text-xs">{err}</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
