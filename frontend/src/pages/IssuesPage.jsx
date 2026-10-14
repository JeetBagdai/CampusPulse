import { useState } from 'react'
import IssueCard from '../components/IssueCard'
import { TYPE_META, useStore } from '../store'
import { TypeIcon } from '../components/Icons'

const COLUMNS = [
  { key: 'new', title: 'Dispatched', statuses: ['open', 'assigned'], hint: 'AI work order sent to staff' },
  { key: 'progress', title: 'In progress', statuses: ['in_progress'], hint: 'Staff acknowledged' },
  { key: 'verify', title: 'Verifying', statuses: ['resolved'], hint: 'Waiting for the next reading' },
  { key: 'done', title: 'Verified / closed', statuses: ['verified', 'auto_closed', 'closed'], hint: 'Confirmed by sensors or camera' },
]

export default function IssuesPage() {
  const snap = useStore((s) => s.snap)
  const [type, setType] = useState('all')
  const issues = snap.issues.filter((i) => type === 'all' || i.type === type)
  return (
    <div className="p-3 md:p-4">
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <h1 className="text-xl font-semibold mr-2">Work orders</h1>
        {['all', ...Object.keys(TYPE_META)].map((t) => (
          <button key={t} onClick={() => setType(t)} className={`chip !py-1 ${type === t ? '!bg-emerald-500/25 !text-emerald-200' : ''}`}>
            {t === 'all' ? 'All' : <><TypeIcon type={t} size={12} />{TYPE_META[t].label}</>}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {COLUMNS.map((c) => {
          const list = issues.filter((i) => c.statuses.includes(i.status))
          return (
            <div key={c.key} className="min-w-0 glass p-3">
              <div className="flex items-baseline gap-2 mb-2">
                <div className="font-semibold">{c.title}</div>
                <span className="chip">{list.length}</span>
              </div>
              <div className="text-xs text-slate-500 mb-2">{c.hint}</div>
              <div className="space-y-2">
                {list.map((i) => <IssueCard key={i.id} issue={i} compact={c.key === 'done'} />)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
