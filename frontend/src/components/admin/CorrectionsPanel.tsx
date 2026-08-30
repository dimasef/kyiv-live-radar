import { CheckCircle2, Circle } from 'lucide-react'

import { fetchCorrections, type Correction } from '@/api'
import { useAsyncData } from '@/lib/useAsyncData'
import { ADMIN_WIDTH } from './adminLayout'

const KIND_LABEL: Record<Correction['kind'], string> = {
  false_positive: 'хибна ціль',
  retype: 'тип цілі',
  relocate: 'район',
}

/** Harvested admin corrections + whether the CURRENT parser already agrees —
 * the operator sees which past mistakes the parser has since learned to handle
 * (green) versus still reproduces (grey), i.e. what's left to fix. */
export default function CorrectionsPanel() {
  const { data: items, loaded } = useAsyncData<Correction[]>(fetchCorrections, [], [])

  const resolved = items.filter((c) => c.resolved).length

  return (
    <div className={`${ADMIN_WIDTH} flex flex-col gap-3 px-4 py-4`}>
      <p className="text-xs text-slate-500">
        Виправлення, зібрані з дій в адмінці. Зелена позначка — поточний парсер уже обробляє
        повідомлення правильно; сіра — ще відтворює стару помилку.
      </p>
      {loaded && items.length > 0 && (
        <p className="text-xs text-slate-400">
          Вирішено <span className="font-mono text-phosphor-soft">{resolved}</span> із{' '}
          <span className="font-mono text-slate-200">{items.length}</span>
        </p>
      )}
      {loaded && items.length === 0 && (
        <p className="text-xs text-slate-600">Виправлень ще немає.</p>
      )}
      <ul className="space-y-1.5">
        {items.map((c) => (
          <li
            key={c.id}
            className="flex items-start gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2"
          >
            {c.resolved ? (
              <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-phosphor" />
            ) : (
              <Circle size={15} className="mt-0.5 shrink-0 text-slate-600" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-[11px] uppercase tracking-wide text-slate-500">
                {KIND_LABEL[c.kind]}
              </div>
              <p className="truncate text-sm text-slate-200" title={c.text}>
                {c.text}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
