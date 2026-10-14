// Shared SVG icons (lucide) for issue types, priorities, roles and detection sources.
import { Building2, CalendarX, Camera, Droplets, Gauge, Smartphone, Sparkles, Trash2, Zap } from 'lucide-react'
import { TYPE_META } from '../store'

const TYPE_ICON = {
  ENERGY_WASTE: Zap, WATER_LEAK: Droplets, BIN_OVERFLOW: Trash2, LITTER: Sparkles, UNDERUSED_BOOKING: CalendarX,
}
export const ROLE_ICON = { electrician: Zap, plumber: Droplets, housekeeping: Trash2, estate_manager: Building2 }
const SOURCE_ICON = { cv: Camera, citizen: Smartphone }
const SOURCE_LABEL = { cv: 'camera', citizen: 'student photo' }
const PRIORITY_COLOR = { P1: '#fb7185', P2: '#fb923c', P3: '#fbbf24' }

export function TypeIcon({ type, size = 16, className = '', style }) {
  const Icon = TYPE_ICON[type] || Zap
  return <Icon size={size} className={className} style={{ color: TYPE_META[type]?.color, ...style }} />
}

export function RoleIcon({ role, size = 13 }) {
  const Icon = ROLE_ICON[role] || Building2
  return <Icon size={size} />
}

export function PriorityChip({ p }) {
  return (
    <span className="chip">
      <span className="w-2 h-2 rounded-full" style={{ background: PRIORITY_COLOR[p], boxShadow: `0 0 6px ${PRIORITY_COLOR[p]}` }} />
      {p}
    </span>
  )
}

export function SourceChip({ source }) {
  const Icon = SOURCE_ICON[source] || Gauge
  return <span className="chip"><Icon size={12} />{SOURCE_LABEL[source] || source}</span>
}
