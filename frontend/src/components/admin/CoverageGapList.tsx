import { useTranslation } from 'react-i18next'

import { fetchCoverageGaps, type CoverageGap } from '@/api'
import { useAsyncData } from '@/lib/useAsyncData'

import AdminActionButton from './AdminActionButton'
import CoverageCandidates from './CoverageCandidates'
import { downloadGapExport, openGapExport } from './exportGaps'

/** How many recent raw messages an export re-parses. The on-screen list stays
 * on the server default (a cheap recent window); an export is a deliberate
 * click, so it sweeps far deeper — the file is what gets handed off for
 * gazetteer/parser work. */
const EXPORT_SCAN = 5000
const EXPORT_LIMIT = 500

/** Threat-flavored messages the parser couldn't localize (usually a missing
 * gazetteer entry — the primary accuracy lever). Read-only: the list is a live
 * indicator (it's re-derived by the CURRENT parser on every load, so a fixed
 * gap disappears by itself), and the export is how the batch leaves the app. */
export default function CoverageGapList() {
  const { data: gaps, loaded } = useAsyncData<CoverageGap[]>(fetchCoverageGaps, [], [])

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-3 px-4 py-4">
      <CoverageCandidates />
      <p className="text-xs text-slate-500">
        Повідомлення, які парсер не зміг привʼязати до району, хоч у них є слово, схоже на назву
        місця — найчастіше це відсутній у газетирі топонім. Експортуйте їх у JSON для розбору.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-slate-500">
          Показано {gaps.length} · експорт сканує {EXPORT_SCAN} останніх повідомлень
        </span>
        <AdminActionButton
          label="Експорт JSON"
          tone="accent"
          onRun={async () => {
            const all = await fetchCoverageGaps(EXPORT_LIMIT, EXPORT_SCAN)
            downloadGapExport(all, EXPORT_SCAN)
          }}
        />
        <AdminActionButton
          label="Відкрити"
          onRun={async () => {
            // Open the tab NOW, inside the click gesture — a tab opened after
            // the fetch below would be blocked as a popup.
            const tab = window.open()
            try {
              const all = await fetchCoverageGaps(EXPORT_LIMIT, EXPORT_SCAN)
              openGapExport(all, EXPORT_SCAN, tab)
            } catch (err) {
              tab?.close()
              throw err
            }
          }}
        />
      </div>
      {loaded && gaps.length === 0 && (
        <p className="text-xs text-slate-600">Прогалин не знайдено.</p>
      )}
      <ul className="space-y-1.5">
        {gaps.map((gap) => (
          <GapRow key={gap.raw_message_id} gap={gap} />
        ))}
      </ul>
    </div>
  )
}

function GapRow({ gap }: { gap: CoverageGap }) {
  const { t } = useTranslation()

  return (
    <li className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span className="rounded bg-white/[0.06] px-1.5 py-0.5">
          {t(`target.${gap.detected_target_type}`)}
        </span>
        {gap.source_name && <span>{gap.source_name}</span>}
        {/* Which unknown word admitted this row — without it the operator
            re-reads the message to find what the parser choked on. */}
        {gap.candidates.map((name) => (
          <span key={name} className="rounded bg-amber-400/10 px-1.5 py-0.5 text-amber-200/80">
            {name}
          </span>
        ))}
      </div>
      <p className="mt-1 text-sm text-slate-200">{gap.text}</p>
    </li>
  )
}
