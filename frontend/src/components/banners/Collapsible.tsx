import type { ReactNode } from 'react'

export default function Collapsible({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <span
      className="grid transition-[grid-template-columns] duration-300 ease-out"
      style={{ gridTemplateColumns: open ? '1fr' : '0fr' }}
    >
      <span
        className={`min-w-0 overflow-hidden transition-opacity duration-200 ${
          open ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {children}
      </span>
    </span>
  )
}
