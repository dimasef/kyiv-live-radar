import { useCallback, useEffect, useState } from 'react'

export interface AsyncData<T> {
  data: T
  loaded: boolean
  /** Replace the held value without refetching — for a panel that mutates a row
   * and already knows the new list. */
  setData: React.Dispatch<React.SetStateAction<T>>
  /** Refetch on demand (after a mutation that changes what the server would
   * return). Obeys the same staleness guard as the automatic fetch. */
  reload: () => void
  /** What the last attempt failed with, null when it succeeded.
   *
   * Exposed because `loaded` alone cannot tell "the server said nothing" from
   * "the request never landed", and a panel that renders its empty state for
   * both is lying about the second one. */
  error: Error | null
}

/** Fetch-on-mount / fetch-on-dependency-change, with the stale-response guard
 * built in.
 *
 * Roughly a dozen panels had hand-rolled this as `useState` + `useEffect` +
 * `.then(set)`, and most of them forgot the guard — so switching a filter twice
 * quickly could leave the slower FIRST response painted under the second
 * filter's label. Owning the guard in one place is the point of this hook; the
 * fetcher stays the caller's business.
 *
 * `deps` is the dependency list for the fetcher, exactly as for `useEffect`.
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList,
  initial: T,
): AsyncData<T> {
  const [data, setData] = useState<T>(initial)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [nonce, setNonce] = useState(0)

  // The fetcher is a fresh closure every render; `deps` is what actually says
  // when the request changes, so that is what this hook keys on.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps)

  useEffect(() => {
    let cancelled = false
    setLoaded(false)
    run()
      .then((value) => {
        if (cancelled) return
        setData(value)
        setError(null)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setError(e instanceof Error ? e : new Error(String(e)))
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [run, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  return { data, loaded, setData, reload, error }
}
