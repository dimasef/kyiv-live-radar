import { useState } from 'react'

import { activateSource, deactivateSource, deleteSource, type Source } from '@/api'

import AdminActionButton from './AdminActionButton'
import SourceEditModal from './SourceEditModal'

/** The per-row controls shared by channel and alert rows: edit (modal),
 * enable/disable, and hard-delete. */
export default function SourceActions({
  source,
  onUpdated,
  onDeleted,
}: {
  source: Source
  onUpdated: (s: Source) => void
  onDeleted: (id: number) => void
}) {
  const [editing, setEditing] = useState(false)
  const st = source.stats

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setEditing(true)}
        className="rounded-md border border-white/15 bg-white/[0.04] px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.08]"
      >
        Редагувати
      </button>
      {source.is_active ? (
        <AdminActionButton
          label="Вимкнути"
          tone="warn"
          confirm={`Прибрати «${source.name}» з живого фіду?`}
          onRun={() => deactivateSource(source.id).then(onUpdated)}
        />
      ) : (
        <AdminActionButton label="Увімкнути" tone="accent" onRun={() => activateSource(source.id).then(onUpdated)} />
      )}
      <AdminActionButton
        label="Видалити"
        tone="danger"
        confirm={`НАЗАВЖДИ видалити «${source.name}» РАЗОМ з усіма його ${st.messages_total} повідомленнями та ${st.events_produced} подіями? Це незворотно.`}
        onRun={() => deleteSource(source.id).then(() => onDeleted(source.id))}
      />
      {editing && (
        <SourceEditModal
          source={source}
          onSaved={(s) => {
            onUpdated(s)
            setEditing(false)
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </div>
  )
}
