// Full-screen logo clip (2 s) played on every full page load, then fades into the app.
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'

const shouldPlay = () => !new URLSearchParams(location.search).has('skipintro')

export default function Intro() {
  const [phase, setPhase] = useState(() => (shouldPlay() ? 'play' : 'gone')) // play -> fade -> gone
  const video = useRef(null)
  const setIntroDone = useStore((s) => s.setIntroDone)

  const finish = () => setPhase((p) => (p === 'play' ? 'fade' : p))

  useEffect(() => {
    if (phase === 'gone') { setIntroDone(); return }
    if (phase === 'play') {
      video.current?.play().catch(finish) // autoplay blocked: skip straight to the app
      const failsafe = setTimeout(finish, 4500) // never hold the app back if the clip stalls
      return () => clearTimeout(failsafe)
    }
    if (phase === 'fade') {
      const t = setTimeout(() => setPhase('gone'), 500)
      return () => clearTimeout(t)
    }
  }, [phase, setIntroDone])

  if (phase === 'gone') return null
  return (
    <div onClick={finish} role="presentation"
      className={`no-print fixed inset-0 z-[90] bg-[#030409] flex items-center justify-center transition-opacity duration-500 ${phase === 'fade' ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
      <video ref={video} src="/intro.mp4" muted playsInline autoPlay preload="auto" onEnded={finish} onError={finish}
        className="w-full h-full object-contain md:object-cover" aria-label="CampusPulse intro" />
    </div>
  )
}
