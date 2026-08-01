import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Friend } from '@/api'
import Avatar from '@/components/common/Avatar'
import { contactStyleOf } from '@/lib/contactMarker'
import { useRadar } from '@/store'

import ContactProfileModal from '../ContactProfileModal'
import MarkerGlyph from '../MarkerGlyph'
import PresenceLine from './PresenceLine'
import { personLabel } from './contactFormat'

/** An accepted contact — the whole row opens their profile (avatar, home
 * controls, remove). The marker glyph on the right previews how they show on the
 * map (dimmed when hidden). */
export default function FriendRow({ friend }: { friend: Friend }) {
  const { t } = useTranslation()
  const style = contactStyleOf(useRadar((s) => s.contactStyles[friend.id]))
  const hidden = useRadar((s) => s.hiddenHomeIds.includes(friend.id))
  const [open, setOpen] = useState(false)

  return (
    <li>
      <button
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] text-slate-300 hover:bg-white/[0.03]"
      >
        <Avatar name={personLabel(friend)} avatarUrl={friend.avatar_url} size={28} />
        <span className="min-w-0 flex-1">
          <span className="block truncate">{personLabel(friend)}</span>
          <PresenceLine online={friend.online} lastSeenAt={friend.last_seen_at} />
        </span>
        {friend.home ? (
          <span className={hidden ? 'opacity-40' : ''}>
            <MarkerGlyph icon={style.icon} color={style.color} />
          </span>
        ) : (
          <span className="text-[10px] text-slate-600">{t('friends.notSharing')}</span>
        )}
        <ChevronRight size={15} className="flex-none text-slate-600" />
      </button>
      {open && <ContactProfileModal contact={friend} onClose={() => setOpen(false)} />}
    </li>
  )
}
