interface Props {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  /** Accessible name; the visible label lives in the row that hosts the switch. */
  label: string
}

/** Small themed toggle switch for the per-type notification filters. The knob
 * needs an explicit `left-0` origin — without it the absolutely-positioned
 * span keeps its static offset and the translate lands outside the track. */
export default function Switch({ checked, onChange, disabled, label }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-[18px] w-8 flex-none rounded-full transition-colors duration-200 ${
        checked ? 'bg-phosphor/60' : 'bg-white/10'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <span
        className={`absolute left-0 top-[2px] h-3.5 w-3.5 rounded-full bg-slate-100 shadow transition-transform duration-200 ${
          checked ? 'translate-x-[15px]' : 'translate-x-[3px]'
        }`}
      />
    </button>
  )
}
