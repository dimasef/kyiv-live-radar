import { useState } from 'react'

import { createSource, type Source } from '@/api'
import type { Region } from '@/types'

import AdminActionButton from './AdminActionButton'
import RegionSelect from './RegionSelect'

/** Subscribe to a new channel in the current tab's role. */
export default function AddSourceForm({ role, onAdded }: { role: Source['role']; onAdded: (s: Source) => void }) {
  const [ref, setRef] = useState('')
  const [region, setRegion] = useState<Region>('kyiv')

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <input
        value={ref}
        onChange={(e) => setRef(e.target.value)}
        placeholder={role === 'alert' ? '@канал тривог' : '@канал, id або t.me/+посилання'}
        className="min-w-0 flex-1 rounded-md border border-white/15 bg-ink-900 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600"
      />
      <RegionSelect
        value={region}
        onChange={setRegion}
        className="rounded-md border border-white/15 bg-ink-900 px-2 py-1 text-xs text-slate-200"
      />
      <AdminActionButton
        label="Додати"
        tone="accent"
        onRun={() =>
          createSource({ subscribe_ref: ref.trim(), role, region }).then((s) => {
            onAdded(s)
            setRef('')
          })
        }
      />
    </div>
  )
}
