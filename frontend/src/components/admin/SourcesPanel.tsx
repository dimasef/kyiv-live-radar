import { useEffect, useState } from 'react'

import { createSource, fetchSources, type Source } from '@/api'

import AdminActionButton from './AdminActionButton'
import AlertRow from './AlertRow'
import ChannelRow from './ChannelRow'

type SubTab = 'channels' | 'alerts'

/** Manage the Telegram sources the radar reads, split into two tabs: spotter
 * «Канали» (produce map events, full quality stats) and «Тривоги» (official
 * air-raid channels, minimal fields). The DB's active sources ARE the live
 * subscription — mutations make the listener reconnect. */
export default function SourcesPanel() {
  const [sources, setSources] = useState<Source[]>([])
  const [loaded, setLoaded] = useState(false)
  const [tab, setTab] = useState<SubTab>('channels')

  useEffect(() => {
    fetchSources()
      .then(setSources)
      .catch(() => {})
      .finally(() => setLoaded(true))
  }, [])

  const replace = (s: Source) => setSources((list) => list.map((x) => (x.id === s.id ? s : x)))
  const upsert = (s: Source) => setSources((list) => [s, ...list.filter((x) => x.id !== s.id)])
  const remove = (id: number) => setSources((list) => list.filter((x) => x.id !== id))

  const channels = sources.filter((s) => s.role === 'spotter')
  const alerts = sources.filter((s) => s.role === 'alert')
  const role: Source['role'] = tab === 'alerts' ? 'alert' : 'spotter'
  const list = tab === 'alerts' ? alerts : channels

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-3 px-4 py-4">
      <div className="flex gap-1">
        <SubTab active={tab === 'channels'} onClick={() => setTab('channels')}>
          Канали ({channels.length})
        </SubTab>
        <SubTab active={tab === 'alerts'} onClick={() => setTab('alerts')}>
          Тривоги ({alerts.length})
        </SubTab>
      </div>

      <p className="text-xs text-slate-500">
        {tab === 'channels'
          ? 'Канали спостерігачів — джерело подій на карті. Активні є списком живої підписки: додавання, вимкнення чи зміна ролі змушує слухача перепідключитися.'
          : 'Офіційні канали тривог — їхні повідомлення йдуть у парсер тривог, а не на карту.'}
      </p>

      <AddSourceForm role={role} onAdded={upsert} />

      {loaded && list.length === 0 && (
        <p className="text-xs text-slate-600">
          {tab === 'channels' ? 'Каналів немає.' : 'Каналів тривог немає.'}
        </p>
      )}
      <ul className="space-y-1.5">
        {list.map((s) =>
          tab === 'alerts' ? (
            <AlertRow key={s.id} source={s} onUpdated={replace} onDeleted={remove} />
          ) : (
            <ChannelRow key={s.id} source={s} onUpdated={replace} onDeleted={remove} />
          ),
        )}
      </ul>
    </div>
  )
}

function SubTab({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
        active ? 'bg-white/[0.08] text-slate-100' : 'text-slate-500 hover:text-slate-300'
      }`}
    >
      {children}
    </button>
  )
}

function AddSourceForm({ role, onAdded }: { role: Source['role']; onAdded: (s: Source) => void }) {
  const [ref, setRef] = useState('')

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <input
        value={ref}
        onChange={(e) => setRef(e.target.value)}
        placeholder={role === 'alert' ? '@канал тривог' : '@канал, id або t.me/+посилання'}
        className="min-w-0 flex-1 rounded-md border border-white/15 bg-ink-900 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600"
      />
      <AdminActionButton
        label="Додати"
        tone="accent"
        onRun={() =>
          createSource({ subscribe_ref: ref.trim(), role }).then((s) => {
            onAdded(s)
            setRef('')
          })
        }
      />
    </div>
  )
}
