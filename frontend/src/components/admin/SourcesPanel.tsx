import { useState } from 'react'

import { fetchSources, type Source } from '@/api'
import { useAsyncData } from '@/lib/useAsyncData'

import AddSourceForm from './AddSourceForm'
import AlertRow from './AlertRow'
import ChannelRow from './ChannelRow'
import SourceSubTab from './SourceSubTab'

type SubTab = 'channels' | 'alerts'

/** Manage the Telegram sources the radar reads, split into two tabs: spotter
 * «Канали» (produce map events, full quality stats) and «Тривоги» (official
 * air-raid channels, minimal fields). The DB's active sources ARE the live
 * subscription — mutations make the listener reconnect. */
export default function SourcesPanel() {
  const [tab, setTab] = useState<SubTab>('channels')
  const { data: sources, loaded, setData: setSources } = useAsyncData<Source[]>(
    fetchSources,
    [],
    [],
  )

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
        <SourceSubTab active={tab === 'channels'} onClick={() => setTab('channels')}>
          Канали ({channels.length})
        </SourceSubTab>
        <SourceSubTab active={tab === 'alerts'} onClick={() => setTab('alerts')}>
          Тривоги ({alerts.length})
        </SourceSubTab>
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
