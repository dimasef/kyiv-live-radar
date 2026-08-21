import { useCallback } from 'react'

import { fetchDistricts } from '@/api'
import { useAsyncData } from '@/lib/useAsyncData'

const EMPTY = new Map<number, string>()

/** Raion id -> display name, for the journal's own routes.
 *
 * The journal fetches this itself rather than reading the districts slice:
 * `bootstrapApp` only runs on the map route (see store/bootstrap.ts), so a
 * direct load of /journal has an empty store. Both journal tabs need the same
 * lookup, so it lives here instead of being written out twice. */
export function useDistrictNames(): (id: number) => string {
  const { data } = useAsyncData(
    useCallback(
      () => fetchDistricts().then((ds) => new Map(ds.map((d) => [d.id, d.name_uk]))),
      [],
    ),
    [],
    EMPTY,
  )
  return useCallback((id: number) => data.get(id) ?? `#${id}`, [data])
}
