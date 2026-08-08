import { describe, expect, it } from 'vitest'

import { stillCollapsed } from './status'

describe('stillCollapsed', () => {
  it('keeps the pill collapsed through a reload of the SAME alert', () => {
    expect(stillCollapsed({ alert: 42, incident: null }, 42, null)).toBe(true)
  })

  it('opens the banner when a new alert starts', () => {
    expect(stillCollapsed({ alert: 42, incident: null }, 43, null)).toBe(false)
  })

  it('opens the banner when an attack starts inside the alert it was collapsed on', () => {
    // The whole point: a ballistic attack at 03:40 must not arrive as a pill
    // because the pill was shrunk during the quiet hour before it.
    expect(stillCollapsed({ alert: 42, incident: null }, 42, 7)).toBe(false)
    expect(stillCollapsed({ alert: 42, incident: 7 }, 42, 9)).toBe(false)
  })

  it('stays collapsed when the attack it was collapsed on merely ends', () => {
    expect(stillCollapsed({ alert: 42, incident: 7 }, 42, null)).toBe(true)
  })

  it('treats nothing saved as expanded', () => {
    expect(stillCollapsed(null, 42, 7)).toBe(false)
  })

  it('does not carry a collapse from an alert into the alert-free clear banner', () => {
    expect(stillCollapsed({ alert: 42, incident: null }, null, null)).toBe(false)
  })
})
