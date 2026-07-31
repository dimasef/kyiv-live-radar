import { useEffect, useRef, useState } from 'react'

import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'

/** Persisted "already seen" card ids, keyed by user id. */
type SeenMap = Record<string, number[]>

function readSeen(userId: number): Set<number> {
  try {
    const raw = safeGet(STORAGE_KEYS.seenCards)
    const map = raw ? (JSON.parse(raw) as SeenMap) : {}
    return new Set(map[String(userId)] ?? [])
  } catch {
    return new Set()
  }
}

function writeSeen(userId: number, ids: Set<number>): void {
  try {
    const raw = safeGet(STORAGE_KEYS.seenCards)
    const map = raw ? (JSON.parse(raw) as SeenMap) : {}
    map[String(userId)] = [...ids]
    safeSet(STORAGE_KEYS.seenCards, JSON.stringify(map))
  } catch {
    // best-effort — a missed shimmer is harmless
  }
}

/** Ids of cards the user owns but hasn't seen in the collection before — the
 * ones that should play the one-time "just obtained" shimmer. Computed exactly
 * once, the first time this user's collection has loaded; the freshly-seen ids
 * are then persisted immediately, so a later visit finds nothing new.
 *
 * Returns an empty set until `active` (own collection, loaded) and while
 * viewing a friend's collection. Syncing with localStorage is the one genuinely
 * external side-effect here, hence the effect. */
export function useNewCards(userId: number | null, ownedIds: number[], active: boolean): Set<number> {
  const [newIds, setNewIds] = useState<Set<number>>(() => new Set())
  const done = useRef(false)
  const key = ownedIds.join(',')

  useEffect(() => {
    if (!active || userId == null || done.current) return
    done.current = true
    const seen = readSeen(userId)
    const fresh = ownedIds.filter((id) => !seen.has(id))
    if (fresh.length) setNewIds(new Set(fresh))
    writeSeen(userId, new Set([...seen, ...ownedIds]))
    // key stands in for ownedIds (a fresh array each render); once `active` and
    // computed, `done` blocks any re-run regardless.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, userId, key])

  return newIds
}
