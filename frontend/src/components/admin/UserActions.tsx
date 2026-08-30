import { type AdminUser, blockUser, deleteUser, unblockUser } from '@/api'

import AdminActionButton from './AdminActionButton'
import { BLOCK_BLOCKER_TEXT, blockDisabledReason, userLabel } from './userFormat'

/** Block / unblock and delete.
 *
 * Where the backend would refuse (yourself, or any admin) the buttons aren't
 * rendered at all — a muted reason takes their place. That is deliberate:
 * AdminActionButton discards the server's error `detail` and shows a bare
 * «Помилка», so an operator-facing explanation has to be static text here. */
export default function UserActions({
  user,
  currentUserId,
  onUpdated,
  onDeleted,
}: {
  user: AdminUser
  currentUserId: number | null | undefined
  onUpdated: (u: AdminUser) => void
  onDeleted: (id: number) => void
}) {
  const label = userLabel(user)
  const blocked = blockDisabledReason(user, currentUserId)

  if (blocked) {
    return <span className="text-[11px] whitespace-nowrap text-slate-600">{BLOCK_BLOCKER_TEXT[blocked]}</span>
  }

  return (
    <div className="flex flex-wrap justify-end gap-1">
      {user.is_active ? (
        <AdminActionButton
          label="Заблокувати"
          tone="warn"
          compact
          confirm={`Заблокувати «${label}»? Доступ зникне одразу — поточна сесія обірветься на наступному ж запиті. Дію можна скасувати.`}
          onRun={() => blockUser(user.id).then(onUpdated)}
        />
      ) : (
        <AdminActionButton
          label="Розблокувати"
          tone="accent"
          compact
          onRun={() => unblockUser(user.id).then(onUpdated)}
        />
      )}
      <AdminActionButton
        label="Видалити"
        tone="danger"
        compact
        confirm={`Видалити «${label}» НАЗАВЖДИ? Зникнуть акаунт, його способи входу, дружні звʼязки та зібрані картки. Баг-репорти, виправлення парсера й підписки лишаться, але без власника. Скасувати неможливо — якщо треба лише відібрати доступ, блокуйте.`}
        onRun={() => deleteUser(user.id).then(() => onDeleted(user.id))}
      />
    </div>
  )
}
