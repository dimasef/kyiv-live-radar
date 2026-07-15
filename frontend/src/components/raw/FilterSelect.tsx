export default function FilterSelect<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs font-medium text-slate-300 focus:border-phosphor/40 focus:outline-none"
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value} className="bg-ink-950 text-slate-200">
          {opt.label}
        </option>
      ))}
    </select>
  )
}
