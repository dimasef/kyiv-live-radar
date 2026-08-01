import { useTranslation } from 'react-i18next'

import Switch from '@/components/common/Switch'
import { useRadar } from '@/store'

import AddContactForm from './AddContactForm'
import FriendRow from './FriendRow'
import IncomingRow from './IncomingRow'
import OutgoingRow from './OutgoingRow'
import SubList from './SubList'

/** Contacts + shareable home — the profile page's "Контакти" section body.
 * AccountPage already gates on auth and supplies the section heading, so this
 * renders just the controls. */
export default function ContactsSection() {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  const friends = useRadar((s) => s.friends)
  const requests = useRadar((s) => s.friendRequests)
  const shareHome = useRadar((s) => s.shareHome)
  const setShareHome = useRadar((s) => s.setShareHome)
  const sharePresence = useRadar((s) => s.sharePresence)
  const setSharePresence = useRadar((s) => s.setSharePresence)

  return (
    <div className="space-y-4">
      {/* Share-my-home switch (privacy gate) — a home must be set to be useful. */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] text-slate-200">{t('friends.shareHomeLabel')}</p>
          <p className="text-[11px] leading-snug text-slate-500">
            {home ? t('friends.shareHomeHint') : t('friends.needHome')}
          </p>
        </div>
        <Switch
          checked={shareHome}
          disabled={!home}
          label={t('friends.shareHomeLabel')}
          onChange={() => void setShareHome(!shareHome).catch(() => {})}
        />
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] text-slate-200">{t('presence.shareLabel')}</p>
          <p className="text-[11px] leading-snug text-slate-500">{t('presence.shareHint')}</p>
        </div>
        <Switch
          checked={sharePresence}
          label={t('presence.shareLabel')}
          onChange={() => void setSharePresence(!sharePresence).catch(() => {})}
        />
      </div>

      <AddContactForm />

      {requests.incoming.length > 0 && (
        <SubList label={t('friends.incoming')}>
          {requests.incoming.map((r) => (
            <IncomingRow key={r.id} req={r.user} id={r.id} />
          ))}
        </SubList>
      )}
      {requests.outgoing.length > 0 && (
        <SubList label={t('friends.outgoing')}>
          {requests.outgoing.map((r) => (
            <OutgoingRow key={r.id} req={r.user} id={r.id} />
          ))}
        </SubList>
      )}

      <SubList label={t('friends.list')}>
        {friends.length === 0 ? (
          <li className="px-1.5 py-1 text-xs text-slate-600">{t('friends.empty')}</li>
        ) : (
          friends.map((f) => <FriendRow key={f.id} friend={f} />)
        )}
      </SubList>
    </div>
  )
}
