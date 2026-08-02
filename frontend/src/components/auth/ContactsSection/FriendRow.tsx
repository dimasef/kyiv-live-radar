import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Friend } from '@/api'
import Avatar from '@/components/common/Avatar'
import ConfirmModal from '@/components/common/ConfirmModal'
import { navigate, userPath } from '@/router'
import { useRadar } from '@/store'

import ContactMapControls from './ContactMapControls'
import { IconBtn } from './PersonRow'
import PresenceLine from './PresenceLine'
import { personLabel } from './contactFormat'

/** An accepted contact: the name opens their profile page, and every control
 * that acts on them is right there in the row — no edit mode to enter first, so
 * restyling their marker or taking it off the map is a single click.
 *
 * The name is its own button rather than the whole row being one: the controls
 * beside it are interactive too, and a button can't contain buttons.
 *
 * One line at every width, so a list of contacts has a single shape to scan and
 * the controls stay unambiguously attached to the name they sit beside. That
 * costs the controls their labels — see ContactMapControls for why the trade
 * goes this way. */
export default function FriendRow({ friend }: { friend: Friend }) {
  const { t } = useTranslation()
  const unfriend = useRadar((s) => s.unfriend)
  const [asking, setAsking] = useState(false)

  return (
    <li className="rounded-md px-1.5 py-1.5 text-[13px] text-slate-300 hover:bg-white/[0.03]">
      <div className="flex items-center gap-2">
        <button
          onClick={() => navigate(userPath(friend.id))}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <Avatar name={personLabel(friend)} avatarUrl={friend.avatar_url} size={28} />
          <span className="min-w-0 flex-1">
            <span className="block truncate">{personLabel(friend)}</span>
            <PresenceLine online={friend.online} lastSeenAt={friend.last_seen_at} />
          </span>
        </button>

        <ContactMapControls friend={friend} />
        <IconBtn
          onClick={() => setAsking(true)}
          label={t('friends.remove')}
          className="text-slate-600 hover:bg-red-400/10 hover:text-red-300"
        >
          <Trash2 size={14} />
        </IconBtn>
      </div>

      {asking && (
        <ConfirmModal
          message={t('friends.removeConfirm', { name: personLabel(friend) })}
          confirmLabel={t('friends.remove')}
          cancelLabel={t('friends.cancel')}
          tone="danger"
          onConfirm={() => void unfriend(friend.id).catch(() => {})}
          onCancel={() => setAsking(false)}
        />
      )}
    </li>
  )
}
