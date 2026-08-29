import { describe, expect, it } from 'vitest'

import type { RegionInfo } from '@/types'

import { inFollowedRegion, stillCollapsed } from './status'

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

describe('inFollowedRegion', () => {
  // The server catalogue: `is_home` is the deployment's own region, never a
  // hardcoded id here.
  const catalogue = [
    { id: 'kyiv', name_uk: 'Київщина', is_home: true, active: true },
    { id: 'sumy', name_uk: 'Сумщина', is_home: false, active: true },
  ] as unknown as RegionInfo[]

  const kyivAlert = { id: 1, region: 'kyiv' as const }
  const sumyAlert = { id: 2, region: 'sumy' as const }

  it('drops another oblast\'s alert for a reader following Сумщина', () => {
    // The 2026-08-29 report: region set to Сумщина, Kyiv's air-raid alert still
    // shown as the reader's own situation.
    expect(inFollowedRegion([kyivAlert], catalogue, 'sumy')).toEqual([])
  })

  it('keeps the followed region\'s own alert', () => {
    expect(inFollowedRegion([kyivAlert, sumyAlert], catalogue, 'sumy')).toEqual([sumyAlert])
  })

  it('falls back to the home region before the picker is answered', () => {
    expect(inFollowedRegion([kyivAlert, sumyAlert], catalogue, null)).toEqual([kyivAlert])
  })

  it('honours an explicit choice even before the catalogue lands', () => {
    // The choice is the reader's own statement of where they are; it does not
    // need the catalogue to be trustworthy.
    expect(inFollowedRegion([kyivAlert], [], 'sumy')).toEqual([])
  })

  it('narrows nothing when there is no followed region at all', () => {
    // First paint with no choice made: failing towards showing an alert is the
    // only safe direction.
    expect(inFollowedRegion([kyivAlert, sumyAlert], [], null)).toHaveLength(2)
  })
})
