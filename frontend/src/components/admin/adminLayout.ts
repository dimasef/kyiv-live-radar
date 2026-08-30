import { THREAT_PATHS } from '@/threatIcons'
import type { TargetType } from '@/types'

/** One content width for every admin panel, tabs and «Весь Фід» included.
 *
 * The console is a desktop tool read on the machine the radar is operated
 * from, and at the reading width the rest of the app uses (max-w-3xl) two
 * thirds of a wide screen were empty margin while source rows, filter bars and
 * message rows wrapped for no reason. Kept as one constant rather than a class
 * per panel so the tab strip and the panel under it can never drift apart.
 */
export const ADMIN_WIDTH = 'mx-auto w-full max-w-[1600px]'

/** Every target type an operator may assign, derived from the icon table rather
 * than listed by hand.
 *
 * `THREAT_PATHS` is a `Record<TargetType, string>`, so the compiler forces it to
 * hold exactly one key per type — a new type in the union cannot ship without
 * appearing here too. The hand-written list this replaces had gone stale: it was
 * missing `kab`, which meant an operator simply could not label a КАБ, months
 * after the type shipped.
 */
export const ADMIN_TARGET_TYPES = Object.keys(THREAT_PATHS) as TargetType[]
