// First-visit welcome: what CampusPulse is, and two ways in (guided demo or explore).
import { useEffect } from 'react'
import { Box, Eye, PlayCircle, Sparkles, X } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useStore } from '../store'

const SEEN_KEY = 'cp_welcome_v1'

function seen() {
  try { return localStorage.getItem(SEEN_KEY) === '1' } catch { return false }
}
function markSeen() {
  try { localStorage.setItem(SEEN_KEY, '1') } catch { /* private mode: show again next time */ }
}

const PILLARS = [
  [Eye, 'Computer vision', 'YOLO spots empty rooms with lights on; a custom-trained model detects overflowing bins (90% accurate).'],
  [Box, 'Digital twin', 'Real campus buildings in 3D. Every issue is shown live and priced in rupees and CO₂.'],
  [Sparkles, 'Generative AI', 'Work orders reach staff phones in their language, fixes are verified, and the NAAC report writes itself.'],
]

export default function Welcome() {
  const { welcomeOpen, setWelcome, startTour, campus } = useStore()
  const bot = useStore((s) => s.snap?.bot?.username)
  const telegram = useStore((s) => s.snap?.channel === 'telegram')

  // ?skipintro hides the welcome (screenshots, embeds)
  useEffect(() => { if (!seen() && !new URLSearchParams(location.search).has('skipintro')) setWelcome(true) }, [setWelcome])
  if (!welcomeOpen) return null
  const close = () => { markSeen(); setWelcome(false) }
  const judgeLink = bot ? `https://t.me/${bot}?start=judge` : null

  return (
    <div className="no-print fixed inset-0 z-[70] flex items-center justify-center p-3 bg-black/50 backdrop-blur-sm">
      <div className="glass-strong w-full max-w-[720px] max-h-[92vh] overflow-auto p-5 md:p-7 pop">
        <div className="flex items-start gap-3">
          <img src="/favicon.svg" className="w-10 h-10" alt="" />
          <div>
            <div className="text-2xl md:text-3xl font-extrabold tracking-tight">CampusPulse</div>
            <div className="text-slate-300 mt-1">A continuous green audit: a live digital twin that finds campus waste with computer vision, gets it fixed, and proves it.</div>
          </div>
          <button className="btn !p-1.5 ml-auto shrink-0" onClick={close} title="Close"><X size={16} /></button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 mt-5">
          {PILLARS.map(([Icon, title, text]) => (
            <div key={title} className="well p-3.5">
              <div className="w-9 h-9 rounded-xl bg-blue-400/15 ring-1 ring-blue-300/25 flex items-center justify-center mb-2"><Icon size={18} className="text-blue-200" /></div>
              <div className="font-bold">{title}</div>
              <div className="text-xs text-slate-400 mt-1 leading-relaxed">{text}</div>
            </div>
          ))}
        </div>

        <div className="flex flex-col sm:flex-row gap-2 mt-5">
          <button className="btn btn-primary !py-3 flex-1 text-base" onClick={() => { close(); startTour() }}>
            <PlayCircle size={18} /> Play the 2-minute demo
          </button>
          <button className="btn !py-3 sm:w-48" onClick={close}>Explore on my own</button>
        </div>

        {telegram && judgeLink && (
          <div className="well p-3 mt-4 flex items-center gap-3">
            <div className="bg-white p-1.5 rounded-lg shrink-0 hidden sm:block"><QRCodeSVG value={judgeLink} size={76} /></div>
            <div className="text-sm min-w-0">
              <div className="font-semibold">Get the staff work orders on your own phone</div>
              <div className="text-xs text-slate-400 mt-0.5">Open <a className="text-blue-200 underline break-all" href={judgeLink} target="_blank" rel="noreferrer">{judgeLink.replace('https://', '')}</a> in Telegram, tap Start, then play the demo. You'll receive each work order and can tap Done yourself.</div>
            </div>
          </div>
        )}

        <div className="text-[11px] text-slate-500 mt-4 leading-relaxed">
          {campus?.short_name ? `Modelled on ${campus.short_name}. ` : ''}Building outlines © OpenStreetMap contributors. Sensor readings are simulated; camera and photo detection are real. Everyone viewing this demo shares one live campus.
        </div>
      </div>
    </div>
  )
}
