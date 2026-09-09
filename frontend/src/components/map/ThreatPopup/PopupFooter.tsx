import AnalyzeButton from '@/components/game/AnalyzeButton'
import { showsAnalyzeAffordance } from '@/components/game/analyzeButtonState'
import { isAdminRole } from '@/api'
import { useRadar } from '@/store'
import type { Threat } from '@/types'

import AdminEditButton from './AdminEditButton'
import { HAIRLINE, MONO } from './popupStyles'

/** What you can DO with this target, as opposed to what it is. Analysis on the
 * left, the admin way into the track editor pinned right — the two are
 * unrelated controls and sitting them apart is what stops the pencil reading
 * as part of the analysis.
 *
 * The separator belongs to the row, not to the popup: a target with neither
 * control renders no row at all, because drawing the rule regardless left a
 * hairline hanging off the bottom edge with nothing under it. Shared by the
 * target popup and the impact popup, which differ in everything above it. */
export default function PopupFooter({ threat }: { threat: Threat }) {
  const gamification = useRadar((s) => s.gamification)
  const authed = useRadar((s) => s.authStatus === 'authed')
  const isAdmin = useRadar((s) => isAdminRole(s.user?.role))
  const analyze = gamification && showsAnalyzeAffordance(threat, authed)

  return (
    <>
      {(analyze || isAdmin) && (
        <div
          style={{
            marginTop: 8,
            paddingTop: 8,
            borderTop: `1px solid ${HAIRLINE}`,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          {analyze && <AnalyzeButton threat={threat} />}
          {/* marginLeft rather than `justifyContent: space-between`: with the
              analysis absent, space-between would leave the pencil on the
              left. */}
          {isAdmin && (
            <span style={{ marginLeft: 'auto', display: 'inline-flex' }}>
              <AdminEditButton threat={threat} />
            </span>
          )}
        </div>
      )}
      {import.meta.env.DEV && (
        <div style={{ marginTop: 4, fontSize: 10, opacity: 0.45, fontFamily: MONO }}>
          T{threat.id}
        </div>
      )}
    </>
  )
}
