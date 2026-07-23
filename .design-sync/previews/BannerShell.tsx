import { BannerShell } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

// Plain text children (no extra icon deps) — the shell owns all the styling.
export const Alert = () => (
  <Stage>
    <BannerShell tone="alert" color="#ef4444" role="alert" label="Повітряна тривога" expanded={false} onToggle={() => {}}>
      <span>Повітряна тривога</span>
      <span className="font-mono tabular-nums opacity-90">18:24</span>
    </BannerShell>
  </Stage>
)
export const Attack = () => (
  <Stage>
    <BannerShell tone="attack" color="#f97316" role="alert" label="Комбінований удар" expanded={false} onToggle={() => {}}>
      <span>Комбінований удар · балістика</span>
      <span className="font-mono tabular-nums opacity-90">×9</span>
    </BannerShell>
  </Stage>
)
export const Clear = () => (
  <Stage>
    <BannerShell tone="clear" color="#22c55e" role="status" label="Відбій тривоги" expanded={false} onToggle={() => {}}>
      <span>Відбій тривоги</span>
    </BannerShell>
  </Stage>
)
