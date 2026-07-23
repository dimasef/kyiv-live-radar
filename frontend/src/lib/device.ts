/** Center-pin placement mode (a fixed icon at the screen center + a confirm
 * button) is for touch devices with no hovering cursor; a device with a real
 * mouse gets the cursor-follow ghost and a click-to-drop instead. Read at call
 * time (not cached) so it stays correct if the primary pointer changes. */
export function centerPinMode(): boolean {
  return !window.matchMedia('(hover: hover) and (pointer: fine)').matches
}
