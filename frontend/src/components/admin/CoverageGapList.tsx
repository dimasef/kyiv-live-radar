import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { addGazetteerCandidate, fetchCoverageGaps, type CoverageGap } from '@/api'

import AdminActionButton from './AdminActionButton'

/** Threat-flavored messages the parser couldn't localize (usually a missing
 * gazetteer entry — the primary accuracy lever). The operator captures a
 * toponym candidate per gap for later review/geocoding; adding one drops it
 * from the list. Read-mostly, so a mount fetch is the simplest correct sync. */
export default function CoverageGapList() {
  const [gaps, setGaps] = useState<CoverageGap[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    fetchCoverageGaps()
      .then(setGaps)
      .catch(() => {})
      .finally(() => setLoaded(true))
  }, [])

  const remove = (id: number) => setGaps((gs) => gs.filter((g) => g.raw_message_id !== id))

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-3 px-4 py-4">
      <p className="text-xs text-slate-500">
        Повідомлення, які схожі на загрозу, але парсер не зміг привʼязати до району — найчастіше це
        відсутній у газетирі топонім. Запишіть кандидата, щоб потім додати його після перевірки.
      </p>
      {loaded && gaps.length === 0 && (
        <p className="text-xs text-slate-600">Прогалин не знайдено.</p>
      )}
      <ul className="space-y-1.5">
        {gaps.map((gap) => (
          <GapRow key={gap.raw_message_id} gap={gap} onCaptured={() => remove(gap.raw_message_id)} />
        ))}
      </ul>
    </div>
  )
}

function GapRow({ gap, onCaptured }: { gap: CoverageGap; onCaptured: () => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')

  return (
    <li className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
      <div className="flex items-center gap-2 text-[11px] text-slate-500">
        <span className="rounded bg-white/[0.06] px-1.5 py-0.5">
          {t(`target.${gap.detected_target_type}`)}
        </span>
        {gap.source_name && <span>{gap.source_name}</span>}
      </div>
      <p className="mt-1 text-sm text-slate-200">{gap.text}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Назва топоніма"
          className="min-w-0 flex-1 rounded-md border border-white/15 bg-ink-900 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600"
        />
        <AdminActionButton
          label="Додати кандидата"
          tone="accent"
          onRun={() =>
            addGazetteerCandidate(gap.raw_message_id, name.trim()).then(onCaptured)
          }
        />
      </div>
    </li>
  )
}
