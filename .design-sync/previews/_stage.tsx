import type { ReactNode } from 'react'

/** The ops-console ink surface every component is designed to sit on. The card
 * harness renders on white by default, so each story stages itself on the real
 * dark background (#05080d = ink-950) for a faithful, coherent DS pane. */
export const Stage = ({ children, pad = 16 }: { children: ReactNode; pad?: number }) => (
  <div style={{ background: '#05080d', padding: pad, borderRadius: 12, display: 'inline-block' }}>
    {children}
  </div>
)
