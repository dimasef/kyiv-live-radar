import { Eye } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

/** Live viewer count, shown in the feed header. Hidden when nobody's watching
 * or the count hasn't arrived yet. */
export default function OnlineBadge() {
  const { t } = useTranslation()
  const online = useRadar((s) => s.online)

  if (online == null || online <= 0) return null

  return (
    <span
      className="flex items-center gap-1 font-mono text-[11px] tabular-nums text-slate-400"
      title={t('presence.watching')}
    >
      <Eye size={13} className="flex-none text-phosphor-soft" />
      {online}
    </span>
  )
}
