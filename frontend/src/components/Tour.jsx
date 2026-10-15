// Self-running guided demo: triggers real events on the shared twin and walks through every page
// with captions, so judges can see the full loop without a presenter.
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Pause, Play, RotateCcw, Volume2, VolumeX, X } from 'lucide-react'
import { api, inr } from '../api'
import { useStore } from '../store'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ---- voice-over: the browser's own text-to-speech reads each caption
const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
const VOICE_KEY = 'cp_tour_voice'
let voice = null
function pickVoice() {
  const all = synth?.getVoices() || []
  const en = all.filter((v) => /^en/i.test(v.lang))
  voice = en.find((v) => /en-IN/i.test(v.lang) && /natural|neural/i.test(v.name))
    || en.find((v) => /natural|neural/i.test(v.name))
    || en.find((v) => /en-IN/i.test(v.lang))
    || en.find((v) => /Google (UK|US) English/i.test(v.name))
    || en[0] || null
}
if (synth) { pickVoice(); synth.addEventListener?.('voiceschanged', pickVoice) }

// captions are written for reading; smooth over symbols a voice would trip on
function forSpeech(t) {
  return t
    .replace(/₹\s?([\d,]+(?:\.\d+)?)\/h/g, '$1 rupees an hour')
    .replace(/₹\s?([\d,]+(?:\.\d+)?)/g, '$1 rupees')
    .replace(/CO₂/g, 'C O 2')
    .replace(/\bNAAC\b/g, 'nack')
    .replace(/\b([A-Z]{1,2})-(\d)/g, '$1 $2')
}

function speak(text, onDone) {
  synth.cancel()
  const u = new SpeechSynthesisUtterance(forSpeech(text))
  if (voice) { u.voice = voice; u.lang = voice.lang } else u.lang = 'en-IN'
  u.rate = 1.08
  u.onend = onDone
  u.onerror = onDone
  synth.speak(u)
}
const snap = () => useStore.getState().snap
const OPEN = (i) => !['verified', 'auto_closed', 'closed'].includes(i.status)

async function waitFor(pred, timeout = 20000) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) {
    const v = pred(snap())
    if (v) return v
    await sleep(400)
  }
  return null
}

function buildSteps(campus) {
  const room = campus.live_room
  const roomName = campus.rooms.find((r) => r.id === room)?.name || room
  const wash = campus.rooms.find((r) => r.type === 'washroom' && r.building === room.split('-')[0])?.id
    || campus.rooms.find((r) => r.type === 'washroom').id
  const ctx = {}
  const energyIssue = (s) => s.issues.find((i) => i.target === room && i.type === 'ENERGY_WASTE' && (i.id === ctx.issue || OPEN(i)))

  return [
    {
      title: 'A live digital twin of the campus',
      text: () => `These are the real buildings of ${campus.short_name}. Sensors and cameras feed every room; colours show what's happening right now.`,
      run: async ({ nav, select, phone }) => { nav('/'); select(null); phone(false) },
      dwell: 6500,
    },
    {
      title: 'Someone leaves the lights on',
      text: () => `${roomName} (${room}) has just emptied, but its lights and fans are still running.`,
      run: async ({ select }) => {
        await api.post('/api/demo/inject', { scenario: 'lights_left_on', target: room })
        select(room)
      },
      dwell: 4000,
    },
    {
      title: 'Detected and priced',
      text: (s) => {
        const i = s && energyIssue(s)
        return i ? `Within minutes it's flagged as energy waste costing ${inr(i.rate_inr_hr)} an hour, with a pin on the twin.`
          : 'Within minutes it is flagged as energy waste and priced in rupees per hour.'
      },
      run: async () => {
        const i = await waitFor(energyIssue, 25000)
        if (i) ctx.issue = i.id
      },
      dwell: 5500,
    },
    {
      title: 'An AI work order reaches the right person',
      text: () => 'A work order is written by AI and sent to the Electrical In-charge on Telegram, in the language they chose (English, Hindi or Kannada).',
      run: async ({ phone }) => {
        phone(true)
        const wo = (await waitFor((s) => s.issues.find((i) => i.id === ctx.issue)?.wo, 10000))
        ctx.wo = wo
        await waitFor((s) => s.feed.some((m) => m.dir === 'out' && m.wo === wo), 15000)
      },
      dwell: 7000,
    },
    {
      title: 'Staff tap Done, the twin double-checks',
      text: () => 'The staff member taps Done on their phone. CampusPulse only marks it fixed after the next camera or sensor reading confirms it.',
      run: async () => {
        if (ctx.wo) await api.post('/api/wa/simulate', { role: 'electrician', text: 'Done', button_id: `DONE:${ctx.wo}` })
        await waitFor((s) => s.issues.find((i) => i.id === ctx.issue)?.status === 'verified', 15000)
      },
      dwell: 5000,
    },
    {
      title: 'Verified fix, money saved',
      text: (s) => {
        const i = s?.issues.find((x) => x.id === ctx.issue)
        return i?.saved_inr ? `Verified: ${inr(i.saved_inr)} saved and logged for the green audit.` : 'Verified, and the saving is logged for the green audit.'
      },
      run: async ({ phone }) => { phone(false) },
      dwell: 5000,
    },
    {
      title: 'A leak at night',
      text: () => `A washroom water meter (${wash}) shows water flowing with nobody around. That pattern means a leak.`,
      run: async ({ select }) => {
        await api.post('/api/demo/inject', { scenario: 'leak', target: wash })
        await api.post('/api/demo/speed?x=15')
        select(wash)
        await waitFor((s) => s.issues.some((i) => i.target === wash && i.type === 'WATER_LEAK' && OPEN(i)), 30000)
        await api.post('/api/demo/speed?x=1')
      },
      dwell: 4500,
    },
    {
      title: 'Students can report problems too',
      text: () => 'Every location has a QR code. A student scans it and snaps a photo; computer vision and AI verify the photo before an issue is raised.',
      run: async () => {},
      dwell: 7000,
    },
    {
      title: 'Every issue is tracked to the end',
      text: () => 'Work orders move from dispatched to in progress, verifying and verified. Unanswered urgent ones escalate to the Estate Manager.',
      run: async ({ nav, select }) => { select(null); nav('/issues') },
      dwell: 6500,
    },
    {
      title: 'Computer vision',
      text: () => 'YOLO counts people and checks lights from an ordinary camera, with faces blurred. A custom-trained model sorts bins into empty, half and overflowing (90% accurate). Try a sample photo here.',
      run: async ({ nav }) => nav('/cameras'),
      dwell: 8000,
    },
    {
      title: 'What would a policy save?',
      text: () => 'The what-if engine replays 30 days of campus life with and without a policy, and shows the monthly saving, CO₂ avoided and payback.',
      run: async ({ nav }) => nav('/whatif'),
      dwell: 7500,
    },
    {
      title: 'A green-audit report in one click',
      text: () => 'A NAAC Criterion 7.1 report is written from live data. AI writes the words; every number comes from the engine and is checked.',
      run: async ({ nav }) => nav('/reports'),
      dwell: 7500,
    },
    {
      title: "That's CampusPulse",
      text: () => 'Explore on your own: click any room on the twin, open the staff messages with the Telegram button, or ask the AI to explain a work order.',
      run: async ({ nav }) => nav('/'),
      dwell: null, // last step waits for the user
    },
  ]
}

export default function Tour() {
  const { tourOn, stopTour, campus, select, setPhone } = useStore()
  const snapNow = useStore((s) => s.snap)
  const nav = useNavigate()
  const [step, setStep] = useState(0)
  const [paused, setPaused] = useState(false)
  const [ready, setReady] = useState(false) // current step's action finished
  const steps = useRef(null)
  const token = useRef(0)
  const speechTok = useRef(0)
  const [voiceOn, setVoiceOn] = useState(() => { try { return localStorage.getItem(VOICE_KEY) !== 'off' } catch { return true } })
  const [spoken, setSpoken] = useState(true) // narration for this step has finished
  const [dwelt, setDwelt] = useState(false) // minimum time on this step has passed
  const toggleVoice = () => {
    const on = !voiceOn
    setVoiceOn(on)
    try { localStorage.setItem(VOICE_KEY, on ? 'on' : 'off') } catch { /* private mode */ }
  }

  useEffect(() => {
    if (!tourOn || !campus) return
    steps.current = buildSteps(campus)
    setStep(0); setPaused(false)
  }, [tourOn, campus])

  // run the current step's action, then dwell, then advance
  useEffect(() => {
    if (!tourOn || !steps.current) return
    const my = ++token.current
    const s = steps.current[step]
    setReady(false)
    ;(async () => {
      try { await s.run({ nav, select, phone: setPhone }) } catch { /* keep the tour going */ }
      if (token.current !== my) return
      setReady(true)
    })()
  }, [tourOn, step]) // eslint-disable-line

  // read the caption aloud once the step's action is done (and again after Resume)
  useEffect(() => {
    if (!tourOn || !ready || paused || !voiceOn || !synth || !steps.current) { setSpoken(true); return }
    const s = steps.current[step]
    const text = `${s.title}. ${s.text(useStore.getState().snap)}`
    const my = ++speechTok.current
    const done = () => { if (speechTok.current === my) setSpoken(true) }
    setSpoken(false)
    speak(text, done)
    const failsafe = setTimeout(done, 4000 + text.split(' ').length * 450) // some browsers never fire 'end'
    return () => { speechTok.current++; clearTimeout(failsafe); synth.cancel() }
  }, [tourOn, ready, paused, voiceOn, step])

  useEffect(() => {
    setDwelt(false)
    if (!tourOn || !ready || paused || !steps.current) return
    const s = steps.current[step]
    if (s.dwell == null) return
    const t = setTimeout(() => setDwelt(true), s.dwell)
    return () => clearTimeout(t)
  }, [tourOn, ready, paused, step])

  // move on when both the minimum time and the narration are done
  useEffect(() => {
    if (!tourOn || !dwelt || !spoken || paused || !steps.current) return
    const t = setTimeout(() => setStep((n) => Math.min(n + 1, steps.current.length - 1)), 600)
    return () => clearTimeout(t)
  }, [tourOn, dwelt, spoken, paused])

  if (!tourOn || !steps.current) return null
  const s = steps.current[step]
  const last = step === steps.current.length - 1
  const close = () => { token.current++; synth?.cancel(); stopTour(); setPhone(false) }

  return (
    <div className="no-print fixed z-[60] left-1/2 -translate-x-1/2 bottom-[84px] md:bottom-6 w-[calc(100%-16px)] max-w-[620px] glass-strong p-4 pop">
      <div className="flex items-center gap-2 mb-2">
        <span className="chip !text-[11px]">Guided demo · {step + 1}/{steps.current.length}</span>
        {!ready && <span className="text-[11px] text-blue-200/80 animate-pulse">working on the live twin…</span>}
        {synth && (
          <button className="btn !p-1.5 ml-auto" onClick={toggleVoice} title={voiceOn ? 'Mute the voice-over' : 'Turn the voice-over on'}
            aria-label={voiceOn ? 'Mute the voice-over' : 'Turn the voice-over on'}>
            {voiceOn ? <Volume2 size={15} /> : <VolumeX size={15} />}
          </button>
        )}
        <button className={`btn !p-1.5 ${synth ? '' : 'ml-auto'}`} onClick={close} title="Close the demo"><X size={15} /></button>
      </div>
      <div className="h-1 rounded-full bg-white/10 overflow-hidden mb-3">
        <div className="h-full bg-gradient-to-r from-blue-400 to-blue-300 transition-all duration-500" style={{ width: `${((step + 1) / steps.current.length) * 100}%` }} />
      </div>
      <div className="font-bold text-lg leading-snug">{s.title}</div>
      <div className="text-sm text-slate-300 mt-1 leading-relaxed">{s.text(snapNow)}</div>
      <div className="flex gap-2 mt-3">
        {last ? (
          <>
            <button className="btn" onClick={() => setStep(0)}><RotateCcw size={14} /> Replay</button>
            <button className="btn btn-primary ml-auto" onClick={close}>Explore on my own</button>
          </>
        ) : (
          <>
            <button className="btn" onClick={() => setPaused(!paused)}>{paused ? <><Play size={14} /> Resume</> : <><Pause size={14} /> Pause</>}</button>
            <button className="btn btn-primary ml-auto" disabled={!ready} onClick={() => setStep(step + 1)}>Next <ChevronRight size={15} /></button>
          </>
        )}
      </div>
    </div>
  )
}
