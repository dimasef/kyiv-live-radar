import { describe, expect, it } from 'vitest'

import { clientLabel, shortDevice, sinceLabel } from './onlineFormat'

describe('clientLabel', () => {
  it('reads the browser that a UA actually is, not the ones it claims', () => {
    // Every one of these carries "Chrome" or "Safari" too.
    expect(clientLabel('Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537.36 Edg/120')).toBe(
      'Edge · Windows',
    )
    expect(clientLabel('Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile Safari/537.36')).toBe(
      'Chrome · Android',
    )
    expect(clientLabel('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) CriOS/120 Mobile/15E Safari/604')).toBe(
      'Chrome · iPhone',
    )
    expect(clientLabel('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/17 Safari/605')).toBe(
      'Safari · Mac',
    )
  })

  it('calls the Samsung TV a TV, not an Android phone', () => {
    // Tizen's UA says both, and the difference is why this app has a separate
    // build target at all.
    expect(
      clientLabel('Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit SamsungBrowser/3.0 Safari'),
    ).toBe('Samsung · TV')
  })

  it('falls through to a dash rather than to a wrong guess', () => {
    expect(clientLabel(null)).toBe('—')
    expect(clientLabel('')).toBe('—')
    expect(clientLabel('curl/8.4.0')).toBe('—')
  })
})

describe('sinceLabel', () => {
  const t0 = new Date('2026-09-15T10:00:00Z').getTime()
  const ago = (mins: number) => new Date(t0 - mins * 60_000).toISOString()

  it('says «щойно» under a minute, so a live table is not a row of zeroes', () => {
    expect(sinceLabel(ago(0), t0)).toBe('щойно')
    expect(sinceLabel(ago(0.9), t0)).toBe('щойно')
  })

  it('counts minutes, then hours', () => {
    expect(sinceLabel(ago(7), t0)).toBe('7 хв')
    expect(sinceLabel(ago(60), t0)).toBe('1 год')
    expect(sinceLabel(ago(125), t0)).toBe('2 год 5 хв')
  })
})

describe('shortDevice', () => {
  it('trims a uuid but leaves a short id alone', () => {
    expect(shortDevice('0b9c2f31-4b6e-4f7a-9c1d-2f3a4b5c6d7e')).toBe('0b9c2f31…')
    expect(shortDevice('d-abc123')).toBe('d-abc123')
    expect(shortDevice(null)).toBe('—')
  })
})
