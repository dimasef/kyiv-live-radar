import { useRadar } from '@/store'
import type { Region } from '@/types'

/** Region picker for the Sources tab, driven by the server catalogue so a newly
 * declared region is offerable the day it exists. A region with no coverage yet
 * is still selectable on purpose — tagging a channel is how its raw messages
 * start accumulating for the gazetteer pass. */
export default function RegionSelect({
  value,
  onChange,
  className,
}: {
  value: Region
  onChange: (region: Region) => void
  className: string
}) {
  const regions = useRadar((s) => s.regions)

  return (
    <select
      className={className}
      value={value}
      onChange={(e) => onChange(e.target.value as Region)}
    >
      {regions.map((region) => (
        <option key={region.id} value={region.id}>
          {region.name_uk}
          {region.active ? '' : ' (готується)'}
        </option>
      ))}
    </select>
  )
}
