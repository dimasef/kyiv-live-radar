/** The shared shape of every button in the floating map-control cluster (see
 * MapControls): a 40px glass chip that lights up while its control is engaged.
 *
 * One place on purpose — the three buttons carried three hand-copied class
 * strings that had already drifted (only one of them had `flex-none`), and they
 * sit shoulder to shoulder where any difference shows.
 *
 * The lit state is `.panel--active` (index.css), which mirrors the top bar's
 * active nav pill, so "this is on" reads the same in both places.
 */
export function mapControlClass(active: boolean): string {
  return (
    'panel flex h-10 w-10 flex-none items-center justify-center transition-colors duration-200 ' +
    (active ? 'panel--active text-phosphor-soft' : 'text-slate-300 hover:text-phosphor-soft')
  )
}
