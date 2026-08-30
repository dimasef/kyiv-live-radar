/** Placeholder rows for an admin panel that is still fetching.
 *
 * Skeleton bars rather than a spinner, and sized like the rows they stand in
 * for: every one of these panels used to render its empty state («Порожньо.»,
 * «Немає активних цілей») during the fetch, so a slow request read as a
 * confident "there is nothing here" — the one answer an operator must not be
 * given wrongly.
 */
export default function AdminLoading({ rows = 3 }: { rows?: number }) {
  return (
    <ul className="space-y-1.5" aria-busy="true" aria-label="Завантаження">
      {Array.from({ length: rows }, (_, i) => (
        <li
          key={i}
          className="h-9 animate-pulse rounded-lg border border-white/[0.06] bg-white/[0.03]"
          style={{ animationDelay: `${i * 90}ms` }}
        />
      ))}
    </ul>
  )
}
