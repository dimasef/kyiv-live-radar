import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

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
})
