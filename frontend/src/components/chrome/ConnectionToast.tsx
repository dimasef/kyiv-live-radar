import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

/** Top-center banner (styled like UpdateToast) shown whenever the WS link is
 * down or a resync is in flight — otherwise a stale-after-background session
 * looks silently fine until the user notices the data is old. Auto-hides once
 * `connected && !resyncing`; no dismiss control, since it just reflects live
 * connection state rather than something to defer. */
export default function ConnectionToast() {
  const { t } = useTranslation()
  const connected = useRadar((s) => s.connected)
  const resyncing = useRadar((s) => s.resyncing)

  if (connected && !resyncing) return null

  return (
    <div
      role="status"
      className="panel fixed top-4 left-1/2 z-[2000] flex w-max max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-3 px-4 py-2.5 shadow-xl"
    >
      <span className="whitespace-nowrap text-xs text-slate-200">
        {connected ? t('conn.resyncing') : t('conn.lost')}
      </span>
    </div>
  )
}
