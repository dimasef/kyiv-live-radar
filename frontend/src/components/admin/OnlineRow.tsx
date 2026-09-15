import type { AdminOnlineDevice } from '@/api'
import Avatar from '@/components/common/Avatar'

import { clientLabel, shortDevice, sinceLabel } from './onlineFormat'

const CELL = 'px-3 py-2 align-middle'

/** One connected reader. An account when this device is known to belong to one,
 * «Без акаунта» otherwise — which is the whole reason this table exists next to
 * the accounts one. */
export default function OnlineRow({ device, now }: { device: AdminOnlineDevice; now: number }) {
  const name = device.display_name || device.email
  return (
    <tr className="border-t border-white/[0.06] hover:bg-white/[0.02]">
      <td className={CELL}>
        {device.user_id != null ? (
          <div className="flex items-center gap-2">
            <Avatar name={name || `#${device.user_id}`} avatarUrl={null} size={24} />
            <div className="min-w-0">
              <div className="truncate text-slate-200">{name || `#${device.user_id}`}</div>
              {name && device.email && name !== device.email && (
                <div className="truncate text-[11px] text-slate-500">{device.email}</div>
              )}
            </div>
          </div>
        ) : (
          <span className="text-slate-500">Без акаунта</span>
        )}
      </td>
      <td className={`${CELL} text-slate-300`}>{clientLabel(device.user_agent)}</td>
      <td className={`${CELL} text-slate-400`}>{sinceLabel(device.since, now)}</td>
      <td className={`${CELL} text-slate-400`}>{device.tabs > 1 ? `×${device.tabs}` : ''}</td>
      <td className={`${CELL} font-mono text-[11px] text-slate-500`}>
        {shortDevice(device.device_id)}
      </td>
      <td className={`${CELL} font-mono text-[11px] text-slate-500`}>{device.ip || '—'}</td>
    </tr>
  )
}
