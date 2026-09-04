import type { AdminUser } from '@/api'

/** Pure derivation helpers for the «Юзери» admin tab — kept out of the JSX so
 * they're trivially testable and the row components stay lean. */

/** How to name an account in a list. Unlike `personLabel` in the contacts UI
 * (which is allowed to fall back to a dash), an admin row must ALWAYS be
 * identifiable — a Telegram-only account with no display name still has an id. */
export function userLabel(user: AdminUser): string {
  return user.display_name?.trim() || user.email?.trim() || `#${user.id}`
}

const PROVIDER_LABEL: Record<string, string> = {
  password: 'пароль',
  google: 'Google',
  telegram: 'Telegram',
}

export const providerLabel = (provider: string): string =>
  PROVIDER_LABEL[provider] ?? provider

/** Free-text filter over the loaded page. Matches name, email, provider labels
 * and `#id`, so one box covers every way the operator might look someone up.
 *
 * An empty query returns the SAME array reference, not a copy — the result is
 * computed during render, and a fresh array each keystroke would re-render every
 * row for nothing. */
export function filterUsers(users: AdminUser[], query: string): AdminUser[] {
  const q = query.trim().toLowerCase()
  if (!q) return users
  return users.filter((u) =>
    [
      u.display_name ?? '',
      u.email ?? '',
      `#${u.id}`,
      String(u.id),
      ...u.providers.map(providerLabel),
    ].some((field) => field.toLowerCase().includes(q)),
  )
}

export interface RoleLabel {
  text: string
  title: string
  /** The role claims admin but nothing backs it — role resolution will silently
   * demote this account on its next login. The one thing this tab exists to
   * surface, so it gets a visible warning rather than only a tooltip. */
  stale: boolean
}

/** The role chip: what it says, why, and whether it is about to evaporate. */
export function roleLabel(user: AdminUser): RoleLabel {
  if (user.role === 'user') {
    return { text: 'Користувач', title: 'Звичайний акаунт без доступу до адмінки.', stale: false }
  }
  if (user.role === 'observer') {
    return {
      text: 'Спостерігач',
      title:
        'Бачить місця влучань на своїй мапі під час тривоги — те, що для решти ' +
        'зʼявляється лише в журналі після відбою. Доступу до адмінки не дає.',
      stale: false,
    }
  }
  const admin = user.role === 'admin_g' ? 'Адмін (вручну)' : 'Адмін'
  if (user.role_source === 'manual') {
    return {
      text: admin,
      title: 'Роль admin_g виставлена в базі вручну. Перерахунок при вході її не чіпає.',
      stale: false,
    }
  }
  if (user.role_source === 'allowlist') {
    return {
      text: admin,
      title: 'Роль походить зі змінних середовища ADMIN_EMAILS / ADMIN_TELEGRAM_IDS.',
      stale: false,
    }
  }
  return {
    text: admin,
    title:
      'Роль більше нічим не підкріплена: запису в ADMIN_EMAILS / ADMIN_TELEGRAM_IDS немає, ' +
      'тож при наступному вході вона автоматично впаде до «Користувач».',
    stale: true,
  }
}

/** Why this account's role cannot be changed from here, or null when it can.
 *
 * Your own role is off-limits (demoting yourself locks you out of the console),
 * and so is a role the env allowlist grants — role resolution would hand that
 * one straight back at the next login.
 *
 * Deliberately STRICTER than the backend on the second case: the API does allow
 * pinning an allowlist admin to the manual `admin_g` (which stops the
 * recompute), but offering that would need a third dropdown state for an
 * operation nobody performs — removing the env entry is the real fix. */
export function roleChangeBlockedReason(
  user: AdminUser,
  currentUserId: number | null | undefined,
): 'self' | 'allowlist' | null {
  if (currentUserId != null && user.id === currentUserId) return 'self'
  if (user.role_source === 'allowlist') return 'allowlist'
  return null
}

export const ROLE_BLOCKED_TEXT: Record<'self' | 'allowlist', string> = {
  self: 'Власну роль змінити не можна.',
  allowlist:
    'Роль видана змінними середовища ADMIN_EMAILS / ADMIN_TELEGRAM_IDS. ' +
    'Заберіть запис звідти — інакше вона повернеться при наступному вході.',
}

export type BlockBlocker = 'self' | 'admin'

/** Why this account cannot be blocked, or null when it can.
 *
 * Mirrors the backend guard in api/admin/users.py exactly — the button is hidden
 * rather than left to fail, because AdminActionButton swallows the server's
 * `detail` and renders a bare «Помилка». */
export function blockDisabledReason(
  user: AdminUser,
  currentUserId: number | null | undefined,
): BlockBlocker | null {
  if (currentUserId != null && user.id === currentUserId) return 'self'
  if (user.role !== 'user') return 'admin'
  return null
}

export const BLOCK_BLOCKER_TEXT: Record<BlockBlocker, string> = {
  self: 'це ви',
  admin: 'адміна не блокують',
}
