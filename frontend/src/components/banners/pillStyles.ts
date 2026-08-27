/** The shared shape of every pill in the map's top-centre stack (App.tsx renders
 * that slot as a column): the alert/attack banner, and the layer notice that
 * stacks under it.
 *
 * One place on purpose — the same reasoning as map/controlStyles.ts, only more
 * so: these two sit directly above one another, where a difference in radius,
 * padding or type size reads as a mistake rather than a variation.
 *
 * `pointer-events-auto` is deliberately NOT here. The stack itself is
 * pointer-events-none, and only the banner takes clicks back (it collapses);
 * a notice that nothing can be done to must not become a click target.
 */
export const PILL_CLASS =
  'flex max-w-full items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-2 ' +
  'text-[11.5px] font-semibold backdrop-blur-md sm:gap-2.5 sm:text-[13px]'

/** Tones painted from fixed classes. An `attack` pill is not here: its colour
 * comes from the incident's severity at runtime (see BannerShell). */
export const PILL_TONE = {
  alert: 'border-red-400/40 bg-red-500/15 text-red-200 shadow-[0_0_22px_-4px_rgba(239,68,68,0.6)]',
  clear:
    'border-emerald-400/30 bg-emerald-500/10 text-emerald-300 shadow-[0_0_22px_-4px_rgba(16,185,129,0.5)]',
  /** Chrome, not sky. The phosphor accent is what this app already uses for
   * "this control is engaged" (.panel--active, the lit nav pill), so a pill in
   * it reads as a statement about the interface — never as another thing
   * happening overhead. Blue was the other candidate and is taken twice over:
   * HOME_COLOR and STATUS_COLORS.unseen are both #38bdf8. */
  layer:
    'border-phosphor/40 bg-phosphor/10 text-phosphor shadow-[0_0_22px_-4px_rgba(34,211,238,0.55)]',
} as const
