import { Collapsible } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

// Collapsible animates width between 0fr↔1fr; shown open so the content is
// visible in the card, next to a static label like in the alert banner.
export const Open = () => (
  <Stage>
    <div className="flex items-center text-red-200">
      <span className="font-mono text-xs">ТРИВОГА</span>
      <Collapsible open>
        <span className="pl-2 text-sm">по місту Київ · 18:24</span>
      </Collapsible>
    </div>
  </Stage>
)
export const Collapsed = () => (
  <Stage>
    <div className="flex items-center text-slate-400">
      <span className="font-mono text-xs">ТРИВОГА</span>
      <Collapsible open={false}>
        <span className="pl-2 text-sm">прихований підпис</span>
      </Collapsible>
    </div>
  </Stage>
)
