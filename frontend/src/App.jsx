import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { Box, Camera, ClipboardList, FileText, FlaskConical, Loader2, PlayCircle, Sparkles, SlidersHorizontal } from 'lucide-react'
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

const NAV = [
  { to: '/', label: 'Twin', icon: Box },
  { to: '/issues', label: 'Work orders', short: 'Orders', icon: ClipboardList },
  { to: '/cameras', label: 'Cameras', icon: Camera },
  { to: '/whatif', label: 'What-if', icon: FlaskConical },
  { to: '/reports', label: 'Reports', icon: FileText },
]

function Clock() {
  const clock = useStore((s) => s.snap?.clock)
  const speed = useStore((s) => s.snap?.speed)
  const paused = useStore((s) => s.snap?.paused)
  if (!clock) return null
  const d = new Date(clock)
  return (
    <div className="text-right leading-tight hidden md:block">
      <div className="font-mono text-sm font-semibold">{d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</div>
      <div className="text-[10px] text-slate-400">
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
  const { openCopilot, toggleDemo, togglePhone, phoneOpen, startTour } = useStore()
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
      <header className="no-print glass-bar flex items-center gap-3 md:gap-6 px-3 md:px-5 h-14 border-b border-line relative z-20 shrink-0">
        <div className="flex items-center gap-2 shrink-0">
          <img src="/favicon.svg" className="w-7 h-7" alt="" />
          <span className="font-extrabold tracking-tight">CampusPulse</span>
          {campus && <span className="hidden lg:inline-flex"><span className="chip !text-[11px]">{campus.short_name}</span></span>}
        </div>
        <nav className="hidden md:flex items-center gap-1">
          {NAV.map(({ to, label }) => (
            <NavLink key={to} to={to} end
              className={({ isActive }) => `px-3 py-1.5 rounded-full text-sm font-semibold transition
                ${isActive ? 'bg-blue-400/15 text-blue-100 ring-1 ring-blue-300/30' : 'text-slate-400 hover:text-slate-100 hover:bg-white/5'}`}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1.5 md:gap-2 shrink-0">
          <Clock />
          <span className={`w-2 h-2 rounded-full mx-1 ${connected ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]' : 'bg-rose-400'}`}
            title={connected ? 'live' : 'offline'} />
          <button className="btn !px-2.5 md:!px-3" onClick={startTour} title="Play the 2-minute guided demo">
            <PlayCircle size={16} /><span className="hidden lg:inline">Play demo</span>
          </button>
          <button className="btn !px-2.5" onClick={toggleDemo} title="Try a scenario (Ctrl+D)"><SlidersHorizontal size={16} /></button>
          <button className="btn btn-primary !px-2.5 md:!px-3.5" onClick={() => openCopilot()}>
            <Sparkles size={16} /><span className="hidden sm:inline">Ask campus</span>
          </button>
        </div>
      </header>

      <main className="flex-1 min-w-0 min-h-0 overflow-auto pb-[68px] md:pb-0">
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
      <nav className="no-print md:hidden fixed bottom-0 inset-x-0 z-30 glass-bar border-t border-line grid grid-cols-5 pb-[env(safe-area-inset-bottom)]">
        {NAV.map(({ to, label, short, icon: Icon }) => (
          <NavLink key={to} to={to} end
            className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[10px] font-semibold ${isActive ? 'text-blue-200' : 'text-slate-400'}`}>
            <Icon size={19} />{short || label}
          </NavLink>
        ))}
      </nav>

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
