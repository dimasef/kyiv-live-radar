import TrackEditModal from '@/components/admin/TrackEditModal'
import { useRadar } from '@/store'

/** The track editor, opened from a target's popup.
 *
 * Deliberately mounted OUTSIDE `<MapContainer>` rather than inside the popup
 * that opens it: «Скасувати ціль» broadcasts back a dismissed track, the store
 * drops it from the map, and the marker — with anything rendered under it —
 * unmounts. A dialog that lived there would vanish mid-edit. The same holds for
 * viewport culling and for the track's own auto-close while it is being read.
 *
 * Hidden (not closed) during a map pick, so the operator can see the map they
 * are picking on; it remounts from the store's copy once the pick lands. */
export default function AdminTrackEditor() {
  const track = useRadar((s) => s.adminTrack)
  const picking = useRadar((s) => s.regroupPick != null)
  const applyAdminTrack = useRadar((s) => s.applyAdminTrack)
  const closeAdminTrack = useRadar((s) => s.closeAdminTrack)
  const startRegroupPick = useRadar((s) => s.startRegroupPick)

  if (track == null || picking) return null

  return (
    <TrackEditModal
      track={track}
      onClose={closeAdminTrack}
      onTrackChanged={applyAdminTrack}
      // The map and the feed both update from the server's websocket
      // broadcast, so there is no list here for these to re-point.
      onEventMoved={() => {}}
      onEventDeleted={() => {}}
      onPickOnMap={(event) =>
        startRegroupPick({ eventId: event.id, sourceThreatId: track.id })
      }
    />
  )
}
