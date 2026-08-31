import type L from 'leaflet'
import { Loader2, MapPin, Search, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { fetchGeocode } from '@/api'
import { currentRegion } from '@/lib/regions'
import { useRadar } from '@/store'
import type { GeocodeHit } from '@/types'

/** Shorter and the query matches half the gazetteer; the backend enforces the
 * same floor. */
const MIN_QUERY = 3
/** Long enough that typing a street name is one lookup, not ten — we are a
 * guest on OSM's rate limit. */
const DEBOUNCE_MS = 400
/** Close enough to pick out a building, wide enough to still recognise the
 * block around it. */
const ADDRESS_ZOOM = 16

/** Address lookup shown while placing a home marker. It only moves the camera
 * — the reader still drops the pin themselves, because a geocoder answers with
 * a building's centre and only they know which side of it they live on. */
export default function AddressSearch({ map }: { map: L.Map | null }) {
  const { t } = useTranslation()
  const region = currentRegion({
    regions: useRadar((s) => s.regions),
    chosenRegion: useRadar((s) => s.chosenRegion),
  })

  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<GeocodeHit[]>([])
  const [busy, setBusy] = useState(false)
  const [searched, setSearched] = useState(false)
  const timer = useRef<number | null>(null)
  const inFlight = useRef<AbortController | null>(null)

  // Timers and an in-flight request are outside React; leaving placement mode
  // unmounts this while both may still be pending.
  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current)
      inFlight.current?.abort()
    },
    [],
  )

  const search = async (value: string) => {
    inFlight.current?.abort()
    const run = new AbortController()
    inFlight.current = run
    setBusy(true)
    try {
      setHits(await fetchGeocode(value, region, run.signal))
      setSearched(true)
    } catch {
      if (!run.signal.aborted) {
        setHits([])
        setSearched(true)
      }
    } finally {
      if (!run.signal.aborted) setBusy(false)
    }
  }

  const onChange = (value: string) => {
    setQuery(value)
    setSearched(false)
    if (timer.current) window.clearTimeout(timer.current)
    if (value.trim().length < MIN_QUERY) {
      inFlight.current?.abort()
      setHits([])
      setBusy(false)
      return
    }
    timer.current = window.setTimeout(() => void search(value.trim()), DEBOUNCE_MS)
  }

  const goTo = (hit: GeocodeHit) => {
    map?.setView([hit.lat, hit.lon], ADDRESS_ZOOM)
    setHits([])
    setSearched(false)
    setQuery(hit.label)
  }

  const clear = () => {
    if (timer.current) window.clearTimeout(timer.current)
    inFlight.current?.abort()
    setQuery('')
    setHits([])
    setSearched(false)
    setBusy(false)
  }

  return (
    <div className="pointer-events-auto absolute left-1/2 top-3 z-[1250] w-[min(94%,28rem)] -translate-x-1/2">
      <div className="relative flex items-center rounded-xl border border-white/10 bg-ink-900 shadow-lg">
        <Search size={16} className="ml-3 flex-none text-slate-500" />
        <input
          autoFocus
          value={query}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') clear()
            if (e.key === 'Enter' && hits[0]) goTo(hits[0])
          }}
          placeholder={t('home.searchPlaceholder')}
          // 16px is not a style choice: iOS Safari zooms the whole page in on a
          // focused input with smaller text, which on this screen means zooming
          // into the map the reader is about to aim at.
          className="min-w-0 flex-1 bg-transparent px-2.5 py-3 text-base text-slate-200 placeholder:text-slate-600 focus:outline-none"
        />
        {busy && <Loader2 size={16} className="mr-3 flex-none animate-spin text-slate-500" />}
        {!busy && query && (
          <button onClick={clear} className="mr-2 p-1 text-slate-500 hover:text-slate-300">
            <X size={16} />
          </button>
        )}
      </div>

      {hits.length > 0 && (
        <ul className="mt-1.5 overflow-hidden rounded-xl border border-white/10 bg-ink-900 shadow-lg">
          {hits.map((hit) => (
            <li key={`${hit.lat},${hit.lon},${hit.label}`}>
              <button
                onClick={() => goTo(hit)}
                className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left hover:bg-white/[0.05]"
              >
                <MapPin size={14} className="flex-none text-phosphor-soft/70" />
                <span className="min-w-0">
                  <span className="block truncate text-sm text-slate-200">{hit.label}</span>
                  {hit.sublabel && (
                    <span className="block truncate text-sm text-slate-500">{hit.sublabel}</span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {searched && !busy && hits.length === 0 && (
        <p className="mt-1.5 rounded-xl border border-white/10 bg-ink-900 px-3 py-2.5 text-sm text-slate-500">
          {t('home.searchEmpty')}
        </p>
      )}
    </div>
  )
}
