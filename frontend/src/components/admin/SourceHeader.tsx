import { ExternalLink } from 'lucide-react'

import type { Source } from '@/api'

import { telegramUrl } from './sourceFormat'

/** Shared row header: active dot, name, and the @handle linking out to the
 * channel on Telegram (when the ref maps to a public URL). No region badge —
 * rows sit under a region heading now (see SourceRegionGroup). */
export default function SourceHeader({ source }: { source: Source }) {
  const url = telegramUrl(source)
  const handle = source.subscribe_ref ?? source.channel_key

  return (
    <div className="flex min-w-0 items-center gap-2">
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${source.is_active ? 'bg-phosphor' : 'bg-slate-600'}`}
        title={source.is_active ? 'активний' : 'вимкнено'}
      />
      <span className="truncate text-sm font-semibold text-slate-100">{source.name}</span>
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex shrink-0 items-center gap-0.5 text-[11px] text-phosphor-soft hover:underline"
        >
          @{handle}
          <ExternalLink size={10} />
        </a>
      ) : (
        <span className="shrink-0 text-[11px] text-slate-500">@{handle}</span>
      )}
    </div>
  )
}
