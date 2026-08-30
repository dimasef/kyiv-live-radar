/** Whether the primary pointer cannot hover — a finger rather than a mouse.
 *
 * Read at call time (not cached) so it stays correct if the primary pointer
 * changes: a tablet with a keyboard case attached mid-session is a real case.
 *
 * Anything whose affordance is a hover has to grow a second, visible form on
 * these devices, because the hover state simply never happens there. Two on the
 * map today: the center-pin placement mode below, and the oblast badges in
 * RegionLayer.
 */
export function touchPrimary(): boolean {
  return !window.matchMedia('(hover: hover) and (pointer: fine)').matches
}

/** Center-pin placement mode (a fixed icon at the screen center + a confirm
 * button) is for touch devices with no hovering cursor; a device with a real
 * mouse gets the cursor-follow ghost and a click-to-drop instead. */
export function centerPinMode(): boolean {
  return touchPrimary()
}
