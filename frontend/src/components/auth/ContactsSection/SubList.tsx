import type { ReactNode } from 'react'

/** A titled group of person rows. */
export default function SubList({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="panel-title mb-1">{label}</p>
      <ul className="-mx-1.5 space-y-0.5">{children}</ul>
    </div>
  )
}
