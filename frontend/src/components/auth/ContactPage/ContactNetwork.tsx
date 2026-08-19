import { ChevronRight } from 'lucide-react'

import type { PublicUser } from '@/api'
import Avatar from '@/components/common/Avatar'
import { navigate, userPath } from '@/router'
import { useRadar } from '@/store'

/** Who this contact is connected to. Names and pictures only — the server
 * withholds the rest (see PublicUserBrief), so there is nothing here to act on.
 *
 * A row leads onward only when that person is a contact of YOURS too: their
 * profile is gated to their own contacts, so any other row would just land on
 * the denial page. */
export default function ContactNetwork({ contacts }: { contacts: PublicUser[] | null }) {
  // Selected as the stored array and narrowed during render. Deriving inside
  // the selector (`s.friends.map(...)`) hands zustand a NEW array on every
  // read, which never compares equal to the last one — an infinite re-render.
  const myFriends = useRadar((s) => s.friends)

  return (
    <div className="panel p-4">
      <h2 className="panel-title mb-3">Контакти</h2>
      {contacts == null ? (
        <p className="text-xs text-slate-600">Завантаження…</p>
      ) : contacts.length === 0 ? (
        <p className="text-xs text-slate-600">Ще немає контактів</p>
      ) : (
        <ul className="space-y-0.5">
          {contacts.map((person) => {
            const label = person.display_name || 'Контакт'
            const mine = myFriends.some((f) => f.id === person.id)
            const body = (
              <>
                <Avatar name={label} avatarUrl={person.avatar_url} size={28} />
                <span className="min-w-0 flex-1 truncate">{label}</span>
                {mine && <ChevronRight size={15} className="flex-none text-slate-600" />}
              </>
            )
            return (
              <li key={person.id}>
                {mine ? (
                  <button
                    onClick={() => navigate(userPath(person.id))}
                    className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] text-slate-300 hover:bg-white/[0.03]"
                  >
                    {body}
                  </button>
                ) : (
                  <span className="flex items-center gap-2 px-1.5 py-1 text-[13px] text-slate-400">
                    {body}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
