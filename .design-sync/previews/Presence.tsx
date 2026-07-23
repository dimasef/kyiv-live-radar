import { Presence } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

// Presence mounts/unmounts its child with an enter/leave animation. Shown
// visible so the banner it wraps is on screen.
export const Visible = () => (
  <Stage>
    <Presence visible>
      <div className="rounded-full border border-phosphor/40 bg-phosphor/10 px-4 py-2 text-sm text-phosphor-soft shadow-[0_0_18px_-4px_rgba(34,211,238,0.5)]">
        Банер зʼявляється плавно
      </div>
    </Presence>
  </Stage>
)
