import { useEffect, useRef, useState } from 'react'
import { Camera, CameraOff, Lightbulb, LightbulbOff } from 'lucide-react'
import { api, inr } from '../api'
import { STATUS_COLOR, TYPE_META, useStore } from '../store'
import { TypeIcon } from '../components/Icons'

const CAM = 'cam-live'
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
          <span className="font-mono text-teal-200">{issue.id}</span>
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
  const target = snap.cv.bindings[CAM]
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

  const start = async () => {
    setErr('')
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
  const waste = det && det.people === 0 && (det.lights_on || det.fans_on)
  const verdict = !det ? null : waste ? 'Empty room with power on' : det.people > 0 ? 'Occupied' : 'Empty, all off'

  return (
    <div className="p-3 md:p-4 max-w-[1300px] mx-auto">
      <div className="glass-panel p-4">
        <div className="flex items-center gap-2 flex-wrap mb-4">
          <h1 className="text-lg font-semibold mr-1">Live camera</h1>
          <span className="chip !bg-rose-500/20 !text-rose-200">
            <span className={`w-2 h-2 rounded-full ${on ? 'bg-rose-400 animate-pulse' : 'bg-slate-500'}`} />{on ? 'LIVE' : 'off'}
          </span>
          <span className="text-sm text-slate-400 ml-2">watches</span>
          <select className="input !py-1 !w-auto text-sm" value={target} onChange={(e) => bind(e.target.value)}>
            {targets.map((t) => <option key={t.id} value={t.id}>{t.id} · {t.name}</option>)}
          </select>
          <div className="ml-auto">
            {on ? <button className="btn" onClick={stop}><CameraOff size={15} /> Stop</button>
              : <button className="btn btn-primary" onClick={start}><Camera size={15} /> Start camera</button>}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-4">
          <div className="relative rounded-2xl overflow-hidden bg-black/60 ring-1 ring-white/10 aspect-[4/3]">
            <video ref={video} className="hidden" muted playsInline />
            <canvas ref={canvas} className="hidden" />
            {det?.annotated ? <img src={det.annotated} className="w-full h-full object-contain" alt="annotated camera feed" draggable={false} />
              : <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm p-8 text-center">
                Start the camera. Frames are analysed on the server with YOLO; faces are blurred and nothing is stored.</div>}
          </div>

          <div className="space-y-3 text-sm">
            {det ? (
              <>
                <div className={`rounded-2xl p-3 font-semibold ${waste ? 'bg-rose-500/20 text-rose-100 ring-1 ring-rose-300/30' : 'bg-emerald-500/15 text-emerald-100 ring-1 ring-emerald-300/20'}`}>{verdict}</div>
                <div className="grid grid-cols-2 gap-2">
                  <Stat label="People" value={det.people} />
                  <Stat label="Lights" value={det.lights_on ? 'ON' : 'OFF'} sub={`brightness ${det.brightness} / ${det.light_threshold}`} />
                  <Stat label="Fan" value={det.fans_on == null ? '…' : det.fans_on ? 'Spinning' : 'Still'} />
                  {isWash && <Stat label="Tap" value={det.tap_on == null ? '…' : det.tap_on ? 'Running' : 'Off'} />}
                  {isBin && <Stat label="Bin (trained model)" value={det.bin_state || '…'} sub={det.bin_state ? `confidence ${det.bin_conf}` : ''} />}
                </div>
              </>
            ) : <div className="text-slate-500">No detections yet.</div>}
            <TwinStatus target={target} />
            <div className="glass p-3">
              <div className="flex items-center mb-2">
                <div className="text-xs text-slate-400">Calibrate light detection</div>
                <span className={`chip ml-auto !text-[11px] ${calib?.calibrated ? '!bg-emerald-500/20 !text-emerald-200' : ''}`}>
                  {calib?.calibrated ? `saved · on ${Math.round(calib.calib.on)} / off ${Math.round(calib.calib.off)}` : calib?.calib?.on || calib?.calib?.off ? 'half done' : 'not calibrated'}
                </span>
              </div>
              <div className="flex gap-2">
                <button className="btn !py-1 flex-1" disabled={!det} onClick={() => calibrate('on')}><Lightbulb size={14} /> Lights ON</button>
                <button className="btn !py-1 flex-1" disabled={!det} onClick={() => calibrate('off')}><LightbulbOff size={14} /> Lights OFF</button>
              </div>
            </div>
            {err && <div className="text-rose-300 text-xs">{err}</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
