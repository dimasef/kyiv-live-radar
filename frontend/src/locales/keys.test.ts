import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { DOWN_LABEL_KEY, STATUS_LABEL_KEY } from '@/threatLabels'

const CHIP_KEYS = { ...STATUS_LABEL_KEY, allClear: 'status.allClear' }

import en from './en.json'
import uk from './uk.json'

/** Every `t('some.key')` written as a plain string literal in the source.
 * Template literals (`t(\`target.${type}\`)`) are deliberately skipped — their
 * key isn't known statically, and those call sites all pass a fallback. */
function usedKeys(dir: string, found = new Map<string, string>()): Map<string, string> {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      usedKeys(path, found)
      continue
    }
    if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) continue
    const src = readFileSync(path, 'utf8')
    for (const m of src.matchAll(/\bt\(\s*(['"])([A-Za-z0-9_.]+)\1/g)) {
      if (!found.has(m[2])) found.set(m[2], path)
    }
  }
  return found
}

function node(bundle: unknown, path: string[]): unknown {
  return path.reduce<unknown>(
    (n, part) => (n && typeof n === 'object' ? (n as Record<string, unknown>)[part] : undefined),
    bundle,
  )
}

/** Whether i18next could resolve `key`. A plural key is stored under suffixed
 * variants (`minutesAgo_one`, `minutesAgo_other`, …) with no bare entry, so the
 * parent object has to be checked for those too. */
function resolves(bundle: unknown, key: string): boolean {
  const path = key.split('.')
  if (typeof node(bundle, path) === 'string') return true
  const parent = node(bundle, path.slice(0, -1))
  if (!parent || typeof parent !== 'object') return false
  const leaf = path[path.length - 1]
  return Object.keys(parent).some((k) => k.startsWith(`${leaf}_`))
}

const KEYS = usedKeys('src')

describe('translation keys', () => {
  it('finds call sites to check (the scan itself still works)', () => {
    expect(KEYS.size).toBeGreaterThan(50)
  })

  // Exists because a `t('close')` typo (real key: `game.close`) shipped the
  // literal string "close" to the UI in every language, silently.
  it.each(['uk', 'en'] as const)('are all present in %s.json', (lang) => {
    const bundle = lang === 'uk' ? uk : en
    const missing = [...KEYS]
      .filter(([key]) => !resolves(bundle, key))
      .map(([key, path]) => `${key}  (${path})`)
    expect(missing).toEqual([])
  })

  // The scan above cannot see a key built from a template literal, and that is
  // precisely where the last gap hid: `t(\`status.${threat.status}\`, fallback)`
  // shipped the raw English "destroyed"/"tracking" to the Ukrainian popup,
  // because only `status.impact` was ever translated. Enum-driven labels now
  // live in a Record whose completeness TypeScript enforces, and every one of
  // its keys has to exist in both bundles.
  it.each(['uk', 'en'] as const)('cover every threat status in %s.json', (lang) => {
    const bundle = lang === 'uk' ? uk : en
    const missing = Object.entries(CHIP_KEYS)
      .filter(([, key]) => !resolves(bundle, key))
      .map(([status, key]) => `${status} -> ${key}`)
    expect(missing).toEqual([])
  })

  // Same class of gap, in the map legend: each target type has its own
  // "shot down" wording because Ukrainian agreement won't survive a
  // «Збитий {{target}}» template, and a missing one would ship the raw key.
  it.each(['uk', 'en'] as const)('cover every legend flip label in %s.json', (lang) => {
    const bundle = lang === 'uk' ? uk : en
    const missing = Object.entries(DOWN_LABEL_KEY)
      .filter(([, key]) => !resolves(bundle, key))
      .map(([type, key]) => `${type} -> ${key}`)
    expect(missing).toEqual([])
  })
})
