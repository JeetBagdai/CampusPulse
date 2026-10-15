// Full-screen intro clip (2 s) played once per browser session, then fades into the app.
import { useEffect, useRef, useState } from 'react'

const KEY = 'cp_intro_played'

function shouldPlay() {
  if (new URLSearchParams(location.search).has('skipintro')) return false
  try { return sessionStorage.getItem(KEY) !== '1' } catch { return true }
}

export default function Intro() {
  const [phase, setPhase] = useState(() => (shouldPlay() ? 'play' : 'gone')) // play -> fade -> gone
  const video = useRef(null)

  const finish = () => setPhase((p) => (p === 'play' ? 'fade' : p))

  useEffect(() => {
    if (phase === 'play') {
      try { sessionStorage.setItem(KEY, '1') } catch { /* private mode: plays again next load */ }
      video.current?.play().catch(finish) // autoplay blocked: skip straight to the app
      const failsafe = setTimeout(finish, 4500) // never hold the app back if the clip stalls
      return () => clearTimeout(failsafe)
    }
    if (phase === 'fade') {
      const t = setTimeout(() => setPhase('gone'), 500)
      return () => clearTimeout(t)
    }
  }, [phase])

  if (phase === 'gone') return null
  return (
    <div onClick={finish} role="presentation"
      className={`no-print fixed inset-0 z-[90] bg-[#030409] flex items-center justify-center transition-opacity duration-500 ${phase === 'fade' ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
      <video ref={video} src="/intro.mp4" muted playsInline autoPlay preload="auto" onEnded={finish} onError={finish}
        className="w-full h-full object-contain md:object-cover" aria-label="CampusPulse intro" />
    </div>
  )
}
