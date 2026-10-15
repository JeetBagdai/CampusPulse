import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { ArrowRight, Box, Camera, ClipboardList, FileText, FlaskConical, Loader2 } from 'lucide-react'
import { useStore } from './store'
import TelegramIcon from './components/TelegramIcon'
import PhonePanel from './components/PhonePanel'
import CopilotDrawer from './components/CopilotDrawer'
import DemoPanel from './components/DemoPanel'
import Tour from './components/Tour'
import Welcome from './components/Welcome'

// pages load on demand: the 3D twin (three.js) and charts don't block the first paint of other pages
const TwinPage = lazy(() => import('./pages/TwinPage'))
const CamerasPage = lazy(() => import('./pages/CamerasPage'))
const IssuesPage = lazy(() => import('./pages/IssuesPage'))
const WhatIfPage = lazy(() => import('./pages/WhatIfPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))

// Cameras is not in the nav: it has its own floating button next to the Telegram one
const NAV = [
  { to: '/', label: 'Home', icon: Box },
  { to: '/issues', label: 'Work', icon: ClipboardList },
  { to: '/whatif', label: 'Projection', icon: FlaskConical },
  { to: '/reports', label: 'Report', icon: FileText },
]

function Clock() {
  const clock = useStore((s) => s.snap?.clock)
  const speed = useStore((s) => s.snap?.speed)
  const paused = useStore((s) => s.snap?.paused)
  if (!clock) return null
  const d = new Date(clock)
  return (
    <div className="text-right leading-tight hidden md:block">
      <div className="font-mono text-sm font-semibold text-neutral-900">{d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</div>
      <div className="text-[10px] text-neutral-500">
        {d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}
        {paused ? ' · paused' : speed > 1 ? ` · ${speed}×` : ''}
      </div>
    </div>
  )
}

const Loading = () => (
  <div className="h-full flex items-center justify-center text-slate-400 gap-2"><Loader2 size={18} className="animate-spin" /> Loading…</div>
)

export default function App() {
  const init = useStore((s) => s.init)
  const ready = useStore((s) => !!s.snap)
  const campus = useStore((s) => s.campus)
  const connected = useStore((s) => s.connected)
  const lastId = useStore((s) => s.snap?.feed?.at(-1)?.id ?? 0)
  const { toggleDemo, togglePhone, phoneOpen, startTour } = useStore()
  const onTwin = useLocation().pathname === '/'
  const seen = useRef(0)
  const [unread, setUnread] = useState(false)

  useEffect(() => { init() }, [init])
  useEffect(() => {
    const onKey = (e) => { if (e.ctrlKey && e.key.toLowerCase() === 'd') { e.preventDefault(); toggleDemo() } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleDemo])
  // dot on the messages button when something new arrives while the drawer is closed
  useEffect(() => {
    if (phoneOpen) { seen.current = lastId; setUnread(false) } else if (lastId > seen.current) setUnread(true)
  }, [lastId, phoneOpen])

  return (
    <div className="h-full flex flex-col">
      {/* floating pill nav: links left, logo centred, demo button right */}
      <header className="no-print navpill fixed z-30 top-3 inset-x-3 md:top-4 md:inset-x-auto md:left-1/2 md:-translate-x-1/2 md:w-[min(1120px,calc(100%-32px))]
        h-14 md:h-16 flex items-center gap-3 px-3 md:px-4">
        <nav className="hidden md:flex items-center gap-0.5">
          {NAV.map(({ to, label }) => (
            <NavLink key={to} to={to} end
              className={({ isActive }) => `px-3.5 py-2 rounded-full text-[15px] transition
                ${isActive ? 'bg-neutral-900/[0.07] text-neutral-950 font-semibold' : 'text-neutral-700 hover:text-neutral-950 hover:bg-neutral-900/[0.04]'}`}>
              {label}
            </NavLink>
          ))}
        </nav>
        <NavLink to="/" className="flex items-center gap-2 shrink-0 md:absolute md:left-1/2 md:-translate-x-1/2">
          <img src="/favicon.svg" className="w-7 h-7" alt="" />
          <span className="font-extrabold tracking-tight text-[17px] text-neutral-950">CampusPulse</span>
          {campus && <span className="hidden xl:inline text-[11px] font-semibold text-neutral-500 bg-neutral-900/[0.06] rounded-full px-2 py-0.5">{campus.short_name}</span>}
        </NavLink>
        <div className="ml-auto flex items-center gap-3 shrink-0">
          <Clock />
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-rose-500'}`} title={connected ? 'live' : 'offline'} />
          <button onClick={startTour} title="Play the 2-minute guided demo"
            className="flex items-center gap-2.5 rounded-[14px] bg-[#4772b3] hover:bg-[#3f67a3] text-white font-semibold text-sm pl-4 pr-1.5 py-1.5 md:py-2 transition shadow-[0_6px_18px_rgba(71,114,179,0.35)]">
            <span>Play demo</span>
            <span className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center"><ArrowRight size={15} /></span>
          </button>
        </div>
      </header>

      <main className={`flex-1 min-w-0 min-h-0 overflow-auto pb-[68px] md:pb-0 ${onTwin ? '' : 'pt-[72px] md:pt-[88px]'}`}>
        {!ready ? <div className="p-10 text-slate-400">Connecting to the campus twin…</div> : (
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<TwinPage />} />
              <Route path="/cameras" element={<CamerasPage />} />
              <Route path="/issues" element={<IssuesPage />} />
              <Route path="/whatif" element={<WhatIfPage />} />
              <Route path="/reports" element={<ReportsPage />} />
            </Routes>
          </Suspense>
        )}
      </main>

      {/* phone: bottom tab bar */}
      <nav className="no-print md:hidden fixed bottom-0 inset-x-0 z-30 glass-bar border-t border-line grid grid-cols-4 pb-[env(safe-area-inset-bottom)]">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end
            className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[10px] font-semibold ${isActive ? 'text-blue-200' : 'text-slate-400'}`}>
            <Icon size={19} />{label}
          </NavLink>
        ))}
      </nav>

      {/* floating camera button (next to Telegram): opens the computer-vision page */}
      {ready && (
        <NavLink to="/cameras" title="Cameras" aria-label="Cameras"
          className={({ isActive }) => `no-print fixed z-40 right-[82px] bottom-[84px] md:bottom-5 w-[54px] h-[54px] rounded-full flex items-center justify-center
            bg-neutral-50 text-neutral-900 shadow-[0_10px_30px_rgba(0,0,0,0.45)] transition hover:scale-105 active:scale-95 ${isActive ? 'ring-2 ring-[#6ea0f5]' : ''}`}>
          <Camera size={22} />
        </NavLink>
      )}
      {/* floating Telegram button: opens the staff messages drawer */}
      {ready && (
        <button onClick={togglePhone} title="Staff messages (Telegram)" aria-label="Staff messages"
          className={`no-print fixed z-40 right-4 bottom-[84px] md:bottom-5 rounded-full shadow-[0_10px_30px_rgba(34,158,217,0.45)]
            transition hover:scale-105 active:scale-95 ${phoneOpen ? 'ring-2 ring-white/70' : ''}`}>
          <TelegramIcon size={54} />
          {unread && <span className="absolute top-0 right-0 w-3.5 h-3.5 rounded-full bg-rose-400 border-2 border-[#1d1d1d]" />}
        </button>
      )}
      {phoneOpen && ready && <PhonePanel />}
      <CopilotDrawer />
      <DemoPanel />
      {ready && <Welcome />}
      {ready && <Tour />}
    </div>
  )
}
