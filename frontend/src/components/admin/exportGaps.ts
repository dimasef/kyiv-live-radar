import type { CoverageGap } from '@/api'

/** The JSON file a gap export produces — the gaps verbatim plus how they were
 * collected, so the file is self-describing when handed off for parser work. */
export interface CoverageGapExport {
  exported_at: string
  /** How many recent raw messages the server re-parsed to find these. */
  scanned: number
  count: number
  gaps: CoverageGap[]
}

function exportBlobUrl(gaps: CoverageGap[], scanned: number) {
  const envelope: CoverageGapExport = {
    exported_at: new Date().toISOString(),
    scanned,
    count: gaps.length,
    gaps,
  }
  const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: 'application/json' })
  return { url: URL.createObjectURL(blob), envelope }
}

/** Trigger a browser download of the gaps as a `.json` file. */
export function downloadGapExport(gaps: CoverageGap[], scanned: number) {
  const { url, envelope } = exportBlobUrl(gaps, scanned)
  const a = document.createElement('a')
  a.href = url
  a.download = `gaps-${envelope.exported_at.replace(/[:.]/g, '-')}.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Open the same JSON in a tab — no file saved. The tab must be opened by the
 * caller INSIDE the click gesture (the export needs a fetch first, and a tab
 * opened after an await is blocked as a popup). The blob URL is revoked on a
 * delay so the tab has time to load it. */
export function openGapExport(gaps: CoverageGap[], scanned: number, tab: Window | null) {
  const { url } = exportBlobUrl(gaps, scanned)
  if (tab == null) {
    URL.revokeObjectURL(url)
    return
  }
  tab.location.href = url
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
