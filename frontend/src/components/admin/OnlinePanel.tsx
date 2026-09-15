import { useEffect } from 'react'

import { type AdminOnline, fetchOnline } from '@/api'
import { useAsyncData } from '@/lib/useAsyncData'
import { useRadar } from '@/store'

import OnlineRow from './OnlineRow'

const COLUMNS = ['Хто', 'Пристрій', 'У застосунку', 'Вкладки', 'ID пристрою', 'IP']
const POLL_MS = 15_000

const EMPTY: AdminOnline = { total: 0, with_account: 0, anonymous: 0, devices: [] }

/** «Зараз онлайн» — everyone in the app this second, including the readers with
 * no account at all.
 *
 * A different question from the accounts table below it, answered by a
 * different thing: `last_seen_at` is stamped on authenticated requests and so
 * can only ever describe people who signed in, while this counts live
 * websockets — one per open tab, held whether or not anyone signed in.
 *
 * Live, never history: the backend keeps this in memory, so it empties on a
 * deploy and there is nothing to look back at. Rows are per DEVICE (a browser
 * profile's own localStorage id), which is why two tabs are one row.
 */
export default function OnlinePanel() {
  const { data, loaded, reload, error } = useAsyncData<AdminOnline>(fetchOnline, [], EMPTY)
  // Already ticking every 10s for the map's freshness; reused here so the
  // «12 хв» labels age without a second timer.
  const now = useRadar((s) => s.nowMs)

  // A timer is genuinely outside React, and this is a live view — the count is
  // wrong the moment anyone opens or closes a tab.
  useEffect(() => {
    const id = setInterval(reload, POLL_MS)
    return () => clearInterval(id)
  }, [reload])

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-xs font-medium text-slate-300">Зараз онлайн</h3>
        {/* «Нікого» is only ever said when the server actually answered:
            an unreachable backend and an empty room look identical otherwise,
            and the first one must not be reported as the second. */}
        {loaded && error == null && (
          <span className="text-[11px] text-slate-500">
            {data.devices.length === 0
              ? 'нікого'
              : `${data.devices.length} читачів · ${data.with_account} з акаунтом · ${data.anonymous} без акаунта · ${data.total} з'єднань`}
          </span>
        )}
        {loaded && error != null && (
          <span className="text-[11px] text-amber-400/80">
            не вдалося прочитати ({error.message})
          </span>
        )}
      </div>
      <p className="text-[11px] text-slate-600">
        Живі з'єднання, не історія: список порожніє при перезапуску бекенда. Рядок — це браузер
        (його власний ID у localStorage), тож дві вкладки — один рядок. Хто без акаунта, той і
        лишається без імені — сокет не несе токена.
      </p>

      {data.devices.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
          <table className="w-full min-w-[720px] text-xs">
            <thead>
              <tr className="bg-white/[0.03] text-left text-[11px] text-slate-500">
                {COLUMNS.map((c) => (
                  <th key={c} className="px-3 py-2 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.devices.map((d, i) => (
                <OnlineRow key={d.device_id ?? `anon-${i}`} device={d} now={now} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
