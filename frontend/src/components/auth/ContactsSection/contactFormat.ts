import type { FriendUserBrief } from '@/api'

export function personLabel(u: FriendUserBrief): string {
  return u.display_name || u.email || '—'
}
