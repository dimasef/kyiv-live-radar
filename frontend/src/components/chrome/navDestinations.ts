import { CalendarClock, FileText, Radar } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { MAP_PATH, RAW_MESSAGES_PATH, THREAT_JOURNAL_PATH } from '@/router'

export interface NavDestination {
  key: string
  path: string
  icon: LucideIcon
  labelKey: string
  /** Only shown to admins (Raw debug view). */
  adminOnly?: boolean
}

/** Primary destinations shown in the TopBar (icons on mobile, icon+label on
 * desktop). Account is intentionally NOT here — the AuthButton already carries
 * account/sign-in, so a separate tab would duplicate it. */
export const NAV_DESTINATIONS: NavDestination[] = [
  { key: 'map', path: MAP_PATH, icon: Radar, labelKey: 'nav.map' },
  { key: 'journal', path: THREAT_JOURNAL_PATH, icon: CalendarClock, labelKey: 'nav.journal' },
  { key: 'raw', path: RAW_MESSAGES_PATH, icon: FileText, labelKey: 'nav.raw', adminOnly: true },
]
