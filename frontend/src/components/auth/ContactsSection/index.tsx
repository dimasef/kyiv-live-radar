import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'

import AddContactForm from './AddContactForm'
import FriendRow from './FriendRow'
import IncomingRow from './IncomingRow'
import OutgoingRow from './OutgoingRow'
import SubList from './SubList'

/** The profile page's "Контакти" section body: who you're connected to, and the
 * requests either way. The two visibility switches that used to sit on top
 * (share my home / show when I was last online) moved into the settings drawer
 * — they're preferences, and the drawer is where every other preference lives.
 * AccountPage gates on auth and supplies the heading, so this renders just the
 * controls. */
export default function ContactsSection() {
  const { t } = useTranslation()
  const friends = useRadar((s) => s.friends)
  const requests = useRadar((s) => s.friendRequests)

  return (
    <div className="space-y-4">
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
