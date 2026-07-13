import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../../store'

// How long the green "відбій" state lingers before disappearing — mirrors the
// store's CLOSED_LINGER_MS pattern for closed tracks (a brief, noticeable
// confirmation rather than an instant vanish).
const CLEAR_LINGER_MS = 8000

function formatDuration(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Persistent strip for the OFFICIAL alert status (тривога/відбій) — answers
 * "is the siren on", a different question from IncidentBanner's "what's
 * flying". City and oblast alerts are independent and both render if open. */
export default function AlertBanner() {
  const { t } = useTranslation()
  const alerts = useRadar((s) => s.alerts)
  const [now, setNow] = useState(() => Date.now())

  const open = alerts.filter((a) => !a.ended_at)
  const mostRecentClosed = alerts.find((a) => a.ended_at)

  const [showClear, setShowClear] = useState(false)
  useEffect(() => {
    if (open.length === 0 && mostRecentClosed) {
      setShowClear(true)
      const timer = setTimeout(() => setShowClear(false), CLEAR_LINGER_MS)
      return () => clearTimeout(timer)
    }
    setShowClear(false)
    return undefined
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mostRecentClosed?.id, mostRecentClosed?.ended_at, open.length])

  // Live duration counter while any alert is open.
  useEffect(() => {
    if (open.length === 0) return undefined
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [open.length])

  if (open.length === 0 && !showClear) return null

  if (open.length > 0) {
    return (
      <div role="status" className="alert-banner pointer-events-none flex flex-wrap justify-center gap-2">
        {open.map((a) => (
          <div
            key={a.id}
            className="flex items-center gap-2.5 rounded-full border border-red-400/40 bg-red-500/15 px-4 py-2 text-[13px] font-semibold text-red-200 backdrop-blur-md shadow-[0_0_22px_-4px_rgba(239,68,68,0.6)]"
          >
            <ShieldAlert size={16} className="flex-none animate-pulse" />
            <span className="uppercase tracking-wide">{t(`alert.scope.${a.scope}`)}</span>
            <span className="font-mono text-[12px] font-medium tabular-nums opacity-90">
              {formatDuration(now - new Date(a.started_at).getTime())}
            </span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div role="status" className="alert-banner pointer-events-none flex justify-center">
      <div className="flex items-center gap-2.5 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-4 py-2 text-[13px] font-semibold text-emerald-300 backdrop-blur-md">
        <ShieldCheck size={16} className="flex-none" />
        <span className="uppercase tracking-wide">{t('alert.clear')}</span>
      </div>
    </div>
  )
}
