import { ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'
import type { SourceLink } from '@/types'

/** One channel: a link out to it where it is public, plain text where it is not.
 *
 * A private channel still gets named — credit is owed either way — but the
 * server withholds its invite link rather than republishing access we were
 * given (see api/public/sources.py). */
function SourceRow({ source }: { source: SourceLink }) {
  const { t } = useTranslation()
  const role = source.role === 'alert' ? t('sourceLinks.alertRole') : null

  const body = (
    <>
      <span className="truncate">{source.name}</span>
      {source.url && <ExternalLink size={11} className="flex-none opacity-60" aria-hidden />}
    </>
  )

  return (
    <li className="text-[13px] leading-tight">
      {source.url ? (
        <a
          href={source.url}
          target="_blank"
          // noreferrer as well as noopener: the target must not be handed this
          // app's URL, and an old browser that ignores noopener still gets one.
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 rounded-lg px-1.5 py-1 text-slate-300 transition-colors hover:bg-white/[0.06] hover:text-phosphor-soft"
        >
          {body}
        </a>
      ) : (
        <span className="flex items-center gap-1.5 px-1.5 py-1 text-slate-400">{body}</span>
      )}
      {role && <span className="block px-1.5 pb-0.5 text-[10px] text-slate-600">{role}</span>}
    </li>
  )
}

/** Who this map is standing on: the spotter channels whose reports become the
 * targets, and the official channel the alert banner comes from.
 *
 * It opens with the legend and above it, because the two answer the same
 * question a beat apart — the legend says what a mark means, this says who
 * saw it. Renders nothing at all until the list has loaded, rather than an
 * empty card: a titled box with no rows reads as "no sources", which is the
 * one thing it must never say. */
export default function SourceLinks() {
  const { t } = useTranslation()
  const sources = useRadar((s) => s.sources)
  if (sources.length === 0) return null

  return (
    <div className="panel popover-up p-3">
      <span className="panel-title mb-2 block px-1.5">{t('sourceLinks.title')}</span>
      <ul className="space-y-0.5">
        {sources.map((s) => (
          <SourceRow key={s.id} source={s} />
        ))}
      </ul>
    </div>
  )
}
