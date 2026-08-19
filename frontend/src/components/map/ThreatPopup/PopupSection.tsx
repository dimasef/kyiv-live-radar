import type { ReactNode } from 'react'

import { HAIRLINE, MONO } from './popupStyles'

/** A labelled block of the popup ("РУХ", "ДАНІ", "ПОВІДОМЛЕННЯ") — a caption in
 * micro-caps with a hairline running out to the edge.
 *
 * Purely presentational: whether a section has anything to say is the calling
 * section's own business, and each of them returns null instead of rendering an
 * empty caption. */
export default function PopupSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
        <span
          style={{
            fontFamily: MONO,
            fontSize: 10,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            opacity: 0.45,
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </span>
        <span style={{ flex: 1, height: 1, background: HAIRLINE }} />
      </div>
      {children}
    </div>
  )
}
