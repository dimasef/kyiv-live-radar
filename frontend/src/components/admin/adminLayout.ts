/** One content width for every admin panel, tabs and «Весь Фід» included.
 *
 * The console is a desktop tool read on the machine the radar is operated
 * from, and at the reading width the rest of the app uses (max-w-3xl) two
 * thirds of a wide screen were empty margin while source rows, filter bars and
 * message rows wrapped for no reason. Kept as one constant rather than a class
 * per panel so the tab strip and the panel under it can never drift apart.
 */
export const ADMIN_WIDTH = 'mx-auto w-full max-w-[1600px]'
