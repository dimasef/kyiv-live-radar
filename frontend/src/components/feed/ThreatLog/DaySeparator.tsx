import { useTranslation } from 'react-i18next'

import { daySeparatorLabel } from './timeline'

export default function DaySeparator({ dayKey }: { dayKey: string }) {
  const { t, i18n } = useTranslation()
  return (
    <li aria-hidden className="flex items-center gap-2 px-1 pt-1.5 first:pt-0">
      <span className="h-px flex-1 bg-white/[0.08]" />
      <span className="font-mono text-[10px] uppercase tracking-wide text-slate-500">
        {daySeparatorLabel(dayKey, i18n.language, t)}
      </span>
      <span className="h-px flex-1 bg-white/[0.08]" />
    </li>
  )
}
