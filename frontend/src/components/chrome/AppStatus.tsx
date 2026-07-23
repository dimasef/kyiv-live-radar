import { Loader2, Wifi, WifiOff } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import TelegramIcon from './TelegramIcon'

const GREEN = '#22c55e'
const RED = '#f87171'
const PHOSPHOR = '#67e8f9'

/** Single fixed status slot for the navbar — one 34×34 icon that reflects every
 * connection state, so nothing pops in/out and shifts the layout. Priority:
 * link lost → reconnecting → Telegram feed down → all good. Hover or tap for a
 * colour-matched tooltip. */
export default function AppStatus() {
  const { t } = useTranslation()
  const connected = useRadar((s) => s.connected)
  const resyncing = useRadar((s) => s.resyncing)
  const feedOk = useRadar((s) => s.feedOk)
  const [open, setOpen] = useState(false)

  let icon: ReactNode
  let tip: string
  let color: string
  if (!connected) {
    color = RED
    tip = t('conn.lost')
    icon = <WifiOff size={16} className="animate-pulse" />
  } else if (resyncing) {
    color = PHOSPHOR
    tip = t('conn.reconnecting')
    icon = <Loader2 size={16} className="animate-spin [animation-duration:1.4s]" />
  } else if (feedOk === false) {
    color = RED
    tip = t('conn.feedLost')
    icon = (
      <span className="relative inline-flex">
        <TelegramIcon size={16} />
        <span className="pointer-events-none absolute left-1/2 top-1/2 h-[1.5px] w-[22px] -translate-x-1/2 -translate-y-1/2 rotate-45 rounded bg-current" />
      </span>
    )
  } else {
    color = GREEN
    tip = t('conn.ok')
    icon = <Wifi size={16} />
  }

  return (
    <div className="group relative flex-none" onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={tip}
        style={{ color, borderColor: `${color}66`, background: `${color}14` }}
        className="flex h-[34px] w-[34px] items-center justify-center rounded-full border"
      >
        {icon}
      </button>
      <span
        role="tooltip"
        style={{ color, borderColor: `${color}55` }}
        className={`pointer-events-none absolute right-0 top-full z-[1300] mt-1.5 whitespace-nowrap rounded-lg border bg-ink-950/95 px-2.5 py-1.5 text-[11px] font-medium shadow-xl transition-opacity duration-150 ${
          open ? 'opacity-100' : 'opacity-0'
        } group-hover:opacity-100`}
      >
        {tip}
      </span>
    </div>
  )
}
