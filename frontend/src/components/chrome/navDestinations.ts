import { CalendarClock, Radar, ShieldCheck } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { ADMIN_PATH, MAP_PATH, THREAT_JOURNAL_PATH } from '@/router'

export interface NavDestination {
  key: string
  path: string
  icon: LucideIcon
  labelKey: string
  /** Only shown to admins (the admin console). */
  adminOnly?: boolean
}

/** Primary destinations shown in the TopBar (icons on mobile, icon+label on
 * desktop). Account is intentionally NOT here — the AuthButton already carries
 * account/sign-in, so a separate tab would duplicate it. */
export const NAV_DESTINATIONS: NavDestination[] = [
  { key: 'map', path: MAP_PATH, icon: Radar, labelKey: 'nav.map' },
  { key: 'journal', path: THREAT_JOURNAL_PATH, icon: CalendarClock, labelKey: 'nav.journal' },
  { key: 'admin', path: ADMIN_PATH, icon: ShieldCheck, labelKey: 'nav.admin', adminOnly: true },
]
