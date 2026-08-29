import { describe, expect, it } from 'vitest'

import type { RegionInfo } from '@/types'

import { stillCollapsed, watchesHomeRegion } from './status'

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

describe('watchesHomeRegion', () => {
  // The server catalogue: `is_home` is the deployment's own region, never a
  // hardcoded id here.
  const catalogue = [
    { id: 'kyiv', name_uk: 'Київщина', is_home: true, active: true },
    { id: 'sumy', name_uk: 'Сумщина', is_home: false, active: true },
  ] as unknown as RegionInfo[]

  it('hides the banner for a reader following another oblast', () => {
    // The 2026-08-29 report: region set to Сумщина, Kyiv's air-raid alert still
    // shown as the reader's own situation.
    expect(watchesHomeRegion(catalogue, 'sumy')).toBe(false)
  })

  it('shows it for a reader following the home region', () => {
    expect(watchesHomeRegion(catalogue, 'kyiv')).toBe(true)
  })

  it('shows it before the picker is answered — that falls back to home', () => {
    expect(watchesHomeRegion(catalogue, null)).toBe(true)
  })

  it('shows it while the catalogue is still empty', () => {
    // First paint, before the boot fetch lands. Failing towards showing an
    // alert is the only safe direction.
    expect(watchesHomeRegion([], 'sumy')).toBe(true)
  })
})
