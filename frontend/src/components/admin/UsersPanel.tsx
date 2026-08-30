import { useState } from 'react'

import { type AdminUser, fetchUsers } from '@/api'
import { useAsyncData } from '@/lib/useAsyncData'
import { useRadar } from '@/store'

import AdminLoading from './AdminLoading'
import { ADMIN_WIDTH } from './adminLayout'
import { filterUsers } from './userFormat'
import UserRow from './UserRow'

const COLUMNS = ['Юзер', 'Роль', 'Стан', 'Входи', 'Реєстрація', 'Останній вхід', 'Активність', '']

/** Every account, newest first, with role changes, blocking and deletion.
 *
 * The role dropdown offers only «Користувач» and «Адмін» (the manual `admin_g`):
 * a plain `admin` is recomputed from the env allowlists at every login, so it
 * cannot be granted here in a way that survives one. A role the allowlist backs
 * shows as read-only «Адмін (env)» for the same reason, and an «Адмін ⚠» is
 * someone whose allowlist entry is gone and who will silently drop to
 * «Користувач» at their next sign-in. */
export default function UsersPanel() {
  const currentUserId = useRadar((s) => s.user?.id ?? null)
  const { data: users, loaded, setData: setUsers } = useAsyncData<AdminUser[]>(
    fetchUsers,
    [],
    [],
  )
  const [query, setQuery] = useState('')

  // Derived during render: one page of rows filters faster than the
  // request-per-keystroke a server-side query param would cost.
  const shown = filterUsers(users, query)

  const replace = (u: AdminUser) => setUsers((list) => list.map((x) => (x.id === u.id ? u : x)))
  const remove = (id: number) => setUsers((list) => list.filter((x) => x.id !== id))

  return (
    <div className={`${ADMIN_WIDTH} flex flex-col gap-3 px-4 py-4`}>
      <p className="text-xs text-slate-500">
        Акаунти застосунку. Блокування забирає доступ одразу — сесія обривається на наступному ж
        запиті, і його можна скасувати. Видалення остаточне.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Пошук за іменем, email, способом входу або #id"
          className="min-w-0 flex-1 rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:border-phosphor/40 focus:outline-none"
        />
        <span className="text-[11px] text-slate-500">
          {query.trim() ? `${shown.length} з ${users.length}` : `${users.length} акаунтів`}
        </span>
      </div>

      {!loaded && <AdminLoading rows={4} />}
      {loaded && users.length === 0 && <p className="text-xs text-slate-600">Акаунтів немає.</p>}
      {loaded && users.length > 0 && shown.length === 0 && (
        <p className="text-xs text-slate-600">Нічого не знайдено.</p>
      )}

      {shown.length > 0 && (
        // Eight columns don't fit a phone: the table scrolls inside its own box
        // rather than making the whole console scroll sideways.
        <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
          <table className="w-full min-w-[900px] text-xs">
            <thead>
              <tr className="bg-white/[0.03] text-left text-[11px] text-slate-500">
                {COLUMNS.map((c, i) => (
                  <th key={c || i} className="px-3 py-2 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  currentUserId={currentUserId}
                  onUpdated={replace}
                  onDeleted={remove}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
