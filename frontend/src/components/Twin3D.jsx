import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { Shape, Vector3 } from 'three'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Edges, Line, OrbitControls } from '@react-three/drei'
import { Camera, LocateFixed } from 'lucide-react'
import { STATUS_COLOR, TYPE_META, useStore } from '../store'
import { TypeIcon } from './Icons'

const ALERT = new Set(['energy', 'water', 'underused', 'litter', 'waste'])
const FLAT = [-Math.PI / 2, 0, 0]

// footprint [[x, z], ...] -> Shape in the x/-z plane (extruded upwards after rotating by FLAT)
function shapeOf(pts) {
  const s = new Shape()
  pts.forEach(([x, z], i) => (i ? s.lineTo(x, -z) : s.moveTo(x, -z)))
  return s
}

function Footprint({ pts, height, color, opacity, edge }) {
  const shape = useMemo(() => shapeOf(pts), [pts])
  return (
    <mesh rotation={FLAT}>
      <extrudeGeometry args={[shape, { depth: height, bevelEnabled: false }]} />
      <meshStandardMaterial color={color} transparent opacity={opacity} depthWrite={false} />
      <Edges color={edge} threshold={20} />
    </mesh>
  )
}

function Flat({ pts, color, opacity }) {
  const shape = useMemo(() => shapeOf(pts), [pts])
  return (
    <mesh rotation={FLAT} position={[0, 0.05, 0]}>
      <shapeGeometry args={[shape]} />
      <meshBasicMaterial color={color} transparent opacity={opacity} depthWrite={false} />
    </mesh>
  )
}

// polylines -> one segment list, so all roads are a single draw call
function segmentsOf(lines, y) {
  const out = []
  for (const { line } of lines) {
    for (let i = 1; i < line.length; i++) out.push([line[i - 1][0], y, line[i - 1][1]], [line[i][0], y, line[i][1]])
  }
  return out
}

// static map + building shells: memoised so the 1 Hz state updates never re-render them
const StaticMap = memo(function StaticMap({ campus }) {
  const { map } = campus
  const roads = useMemo(() => segmentsOf(map.roads, 0.2), [map])
  const paths = useMemo(() => segmentsOf(map.paths, 0.2), [map])
  const fh = campus.floor_height
  return (
    <group>
      {map.boundary && <Line points={map.boundary.map(([x, z]) => [x, 0.3, z])} color="#2dd4bf" lineWidth={1.5} dashed dashSize={8} gapSize={6} transparent opacity={0.5} />}
      {map.pitches.map((p, i) => <Flat key={i} pts={p.footprint} color="#15803d" opacity={0.35} />)}
      {roads.length > 0 && <Line segments points={roads} color="#3b6b72" lineWidth={2.5} />}
      {paths.length > 0 && <Line segments points={paths} color="#2a4f55" lineWidth={1} />}
      {map.context.map((b, i) => <Footprint key={i} pts={b.footprint} height={b.floors * 6} color="#334a52" opacity={0.28} edge="#4b6670" />)}
      {campus.buildings.map((b) => (
        <Footprint key={b.id} pts={b.footprint} height={b.floors * fh + 0.6} color={b.color} opacity={0.06} edge={b.color} />
      ))}
    </group>
  )
})

const RoomBox = memo(function RoomBox({ room, status, selected, hovered, onSelect, onHover }) {
  const mat = useRef()
  const isWash = room.type === 'washroom'
  const color = status === 'idle' ? (isWash ? '#1d3b5c' : STATUS_COLOR.idle) : STATUS_COLOR[status]
  const alert = ALERT.has(status)
  const [x, y, z] = room.pos
  const [w, h, d] = room.size

  useFrame(({ clock }) => {
    if (mat.current && alert) mat.current.emissiveIntensity = 0.35 + 0.35 * Math.sin(clock.elapsedTime * 4)
  })

  return (
    <mesh position={[x, y + h / 2 + 0.3, z]} rotation={[0, room.rot || 0, 0]}
      onPointerMove={(e) => { e.stopPropagation(); onHover(room.id, e.nativeEvent) }}
      onPointerOut={() => onHover(null)}
      onClick={(e) => { e.stopPropagation(); onSelect(room.id) }}>
      <boxGeometry args={[w, h, d]} />
      <meshStandardMaterial ref={mat} color={color} emissive={color} transparent
        emissiveIntensity={status === 'fixed' ? 0.4 : 0.05} opacity={status === 'idle' ? 0.55 : 0.9} roughness={0.5} />
      <Edges color={selected ? '#ffffff' : hovered ? '#94a3b8' : '#2a4a50'} />
    </mesh>
  )
})

const Bin = memo(function Bin({ bin, fill, selected, onSelect }) {
  const f = Math.min(100, fill ?? 0) / 100
  const color = f >= 0.85 ? '#fb7185' : f >= 0.6 ? '#fbbf24' : '#34d399'
  const [x, , z] = bin.pos
  return (
    <group position={[x, 0, z]} scale={2.2} onClick={(e) => { e.stopPropagation(); onSelect(bin.id) }}>
      <mesh position={[0, 1, 0]}>
        <cylinderGeometry args={[0.9, 0.75, 2, 16, 1, true]} />
        <meshStandardMaterial color="#64748b" transparent opacity={0.35} side={2} />
        {selected && <Edges color="#fff" />}
      </mesh>
      <mesh position={[0, Math.max(0.05, f * 2) / 2, 0]}>
        <cylinderGeometry args={[0.8, 0.72, Math.max(0.05, f * 2), 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={f >= 0.85 ? 0.6 : 0.15} />
      </mesh>
    </group>
  )
})

// Shift the rendered image so the campus is centred in the area not covered by the panel/sheet,
// regardless of how the user orbits: left on desktop (side panel), up on phones (bottom sheet).
function ViewOffset() {
  const { camera, size } = useThree()
  useEffect(() => {
    const desktop = size.width >= 768
    camera.setViewOffset(size.width, size.height, desktop ? 120 : 0, desktop ? 0 : size.height * 0.2, size.width, size.height)
    camera.updateProjectionMatrix()
    return () => { camera.clearViewOffset(); camera.updateProjectionMatrix() }
  }, [camera, size.width, size.height])
  return null
}

// One loop moves every DOM overlay (building labels + issue pins) to its 3D anchor each frame.
const _v = new Vector3()
function Projector({ points, els }) {
  useFrame(({ camera, size }) => {
    for (const [id, pos] of points.current) {
      const el = els.current[id]
      if (!el) continue
      _v.set(pos[0], pos[1], pos[2]).project(camera)
      const visible = _v.z < 1 && Math.abs(_v.x) < 1.2 && Math.abs(_v.y) < 1.2
      el.style.display = visible ? '' : 'none'
      el.style.transform = `translate(${((_v.x + 1) / 2) * size.width}px, ${((1 - _v.y) / 2) * size.height}px) translate(-50%, -50%)`
    }
  })
  return null
}

export default function Twin3D() {
  const campus = useStore((s) => s.campus)
  const snap = useStore((s) => s.snap)
  const selected = useStore((s) => s.selected)
  const select = useStore((s) => s.select)
  const [hover, setHover] = useState(null)
  const onHover = useMemo(() => (id, ev) => setHover(id ? { id, x: ev.offsetX, y: ev.offsetY } : null), [])
  const els = useRef({})
  const points = useRef([])
  const controls = useRef()

  const anchors = useMemo(() => {
    const m = {}
    campus.rooms.forEach((r) => { m[r.id] = [r.pos[0], r.pos[1] + r.size[1] + 4, r.pos[2]] })
    campus.bins.forEach((b) => { m[b.id] = [b.pos[0], 9, b.pos[2]] })
    campus.buildings.forEach((b) => { m[`b:${b.id}`] = [b.center[0], b.floors * campus.floor_height + 14, b.center[1]] })
    return m
  }, [campus])

  const open = snap.issues.filter((i) => !['verified', 'auto_closed', 'closed', 'resolved'].includes(i.status))
  const pinned = new Map()
  open.forEach((i) => { if (!pinned.has(i.target)) pinned.set(i.target, i) })
  points.current = [...campus.buildings.map((b) => [`b:${b.id}`, anchors[`b:${b.id}`]]),
    ...[...pinned.keys()].filter((t) => anchors[t]).map((t) => [`p:${t}`, anchors[t]])]

  const hoverRoom = hover && campus.rooms.find((r) => r.id === hover.id)
  const hoverLive = hover && snap.rooms[hover.id]
  const { target, camera } = campus.view

  return (
    <div className="absolute inset-0 overflow-hidden">
      <Canvas camera={{ position: camera, fov: 40, near: 1, far: 5000 }} onPointerMissed={() => select(null)}
        dpr={[1, 1.5]} gl={{ alpha: true, antialias: true, powerPreference: 'high-performance' }}>
        <ambientLight intensity={0.75} />
        <directionalLight position={[300, 500, 200]} intensity={1.1} />
        <ViewOffset />
        <OrbitControls ref={controls} target={target} maxPolarAngle={Math.PI / 2.15} minDistance={40} maxDistance={1600} makeDefault />
        <mesh rotation={FLAT} position={[0, -0.05, 0]}>
          <planeGeometry args={[1500, 1100]} />
          <meshStandardMaterial color="#0a2a30" transparent opacity={0.55} />
        </mesh>
        <gridHelper args={[1500, 75, '#1f5058', '#123a40']} />
        <StaticMap campus={campus} />
        {campus.rooms.map((r) => (
          <RoomBox key={r.id} room={r} status={snap.rooms[r.id]?.status || 'idle'} selected={selected === r.id}
            hovered={hover?.id === r.id} onSelect={select} onHover={onHover} />
        ))}
        {campus.bins.map((b) => (
          <Bin key={b.id} bin={b} fill={snap.bins[b.id]?.fill} selected={selected === b.id} onSelect={select} />
        ))}
        <Projector points={points} els={els} />
      </Canvas>

      {campus.buildings.map((b) => {
        const sc = snap.buildings[b.id]
        return (
          <div key={b.id} ref={(el) => { els.current[`b:${b.id}`] = el }}
            className="glass-strong absolute left-0 top-0 px-2.5 py-1 text-[11px] whitespace-nowrap flex items-center gap-1.5 pointer-events-none !rounded-full">
            <span className="w-2 h-2 rounded-full" style={{ background: b.color, boxShadow: `0 0 8px ${b.color}` }} />
            <span className="font-bold">{b.name}</span>
            {sc && <span className={`font-bold ${sc.score >= 85 ? 'text-emerald-300' : sc.score >= 70 ? 'text-amber-300' : 'text-rose-300'}`}>{sc.score}</span>}
          </div>
        )
      })}
      {[...pinned.values()].map((i) => {
        const meta = TYPE_META[i.type] || {}
        return (
          <button key={i.target} ref={(el) => { els.current[`p:${i.target}`] = el }} onClick={() => select(i.target)}
            className="absolute left-0 top-0 flex items-center justify-center" style={{ display: 'none' }}>
            <span className="absolute w-9 h-9 rounded-full pulse-ring" style={{ background: meta.color }} />
            <span className="relative w-8 h-8 rounded-full flex items-center justify-center shadow-lg border-2 border-white/80" style={{ background: meta.color }}>
              {i.photo ? <Camera size={15} className="text-white" /> : <TypeIcon type={i.type} size={15} style={{ color: '#fff' }} />}
            </span>
          </button>
        )
      })}
      {hoverRoom && (
        <div className="absolute glass px-2 py-1 text-xs whitespace-nowrap pointer-events-none hidden md:block"
          style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <div className="font-semibold">{hoverRoom.id} · {hoverRoom.name}</div>
          {hoverLive && hoverRoom.type !== 'washroom' && <div className="text-slate-300">{hoverLive.occ} people · {hoverLive.power_w} W {hoverLive.cv_live ? '· live camera' : ''}</div>}
          {hoverLive && hoverRoom.type === 'washroom' && <div className="text-slate-300">{hoverLive.flow_lpm} L/min</div>}
        </div>
      )}
      <button className="btn !py-1 !px-3 text-xs absolute left-[104px] bottom-4 max-md:top-[84px] max-md:bottom-auto max-md:left-auto max-md:right-3"
        onClick={() => controls.current?.reset()}>
        <LocateFixed size={13} /> <span className="hidden md:inline">Reset view</span>
      </button>
      <div className="absolute left-[220px] bottom-5 text-[10px] text-slate-500 pointer-events-none hidden md:block">
        {campus.short_name} · building outlines © OpenStreetMap contributors · sensor data simulated
      </div>
    </div>
  )
}
