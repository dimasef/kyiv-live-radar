import { ChevronLeft } from 'lucide-react'
import { useEffect, useState } from 'react'

import { fetchUserCollection, fetchUserContacts, type Collection, type PublicUser } from '@/api'
import Avatar from '@/components/common/Avatar'
import { ACCOUNT_PATH, navigate, useRoute, userRouteId } from '@/router'
import { useRadar } from '@/store'

import CollectionSummaryCard from '../CollectionSummaryCard'
import PresenceLine from '../ContactsSection/PresenceLine'
import { personLabel } from '../ContactsSection/contactFormat'
import ContactNetwork from './ContactNetwork'

/** One contact's profile page (`/user/<id>`): who they are, how their card
 * collection is coming along, and who they're connected to.
 *
 * Read-only by design. Everything that ACTS on a contact — showing their home on
 * the map, restyling their marker, removing them — sits in the contact list on
 * the account page, next to the person it affects.
 *
 * Both fetches are server-gated to that person's accepted contacts, so a
 * hand-typed id for a stranger renders the denial below rather than anything
 * about them. */
export default function ContactPage() {
  const route = useRoute()
  const userId = userRouteId(route)
  const authed = useRadar((s) => s.authStatus === 'authed')
  const gamification = useRadar((s) => s.gamification)
  const contact = useRadar((s) => s.friends.find((f) => f.id === userId) ?? null)

  const [collection, setCollection] = useState<Collection | null>(null)
  const [contacts, setContacts] = useState<PublicUser[] | null>(null)
  const [denied, setDenied] = useState(false)

  // Route-scoped data for someone else — it belongs to this page, not to the
  // store, and it has to be re-fetched when the route's id changes.
  //
  // Only the contact list decides `denied`: it and the page share one gate, so
  // its refusal IS the page's. A collection that fails for any other reason
  // just leaves its card out, rather than claiming you can't see the person.
  useEffect(() => {
    if (userId == null || !authed) return
    setCollection(null)
    setContacts(null)
    setDenied(false)
    fetchUserCollection(userId)
      .then(setCollection)
      .catch(() => {})
    fetchUserContacts(userId)
      .then(setContacts)
      .catch(() => setDenied(true))
  }, [userId, authed])

  if (!authed) return <Centered>Ви не увійшли.</Centered>
  if (userId == null) return <Centered>Такого користувача немає.</Centered>
  if (denied) return <Centered>Профіль доступний лише контактам.</Centered>

  return (
    <div className="h-full overflow-y-auto bg-ink-950 px-4 py-8 text-slate-200">
      <div className="page-col space-y-4">
        <button
          onClick={() => navigate(ACCOUNT_PATH)}
          className="flex items-center gap-1 text-xs text-slate-500 transition-colors hover:text-slate-300"
        >
          <ChevronLeft size={14} /> Контакти
        </button>

        <div className="panel flex items-center gap-4 p-4">
          <Avatar
            name={contact ? personLabel(contact) : '—'}
            avatarUrl={contact?.avatar_url}
            size={72}
          />
          <div className="min-w-0">
            <h1 className="truncate font-display text-lg font-bold text-slate-100">
              {contact ? personLabel(contact) : 'Контакт'}
            </h1>
            {contact && (
              <PresenceLine online={contact.online} lastSeenAt={contact.last_seen_at} />
            )}
          </div>
        </div>

        {/* An empty 0/28 card would be noise for someone who doesn't play, so
            it needs either their cards to show or your own interest in them. */}
        {(gamification || (collection?.total_analyses ?? 0) > 0) && (
          <CollectionSummaryCard collection={collection} userId={userId} />
        )}

        <ContactNetwork contacts={contacts} />
      </div>
    </div>
  )
}

function Centered({ children }: { children: string }) {
  return (
    <div className="flex h-full items-center justify-center bg-ink-950 text-sm text-slate-400">
      {children}
    </div>
  )
}
