interface Props {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  /** Accessible name; the visible label lives in the row that hosts the switch. */
  label: string
}

/** The app's toggle switch, used wherever a setting is a plain yes/no.
 *
 * 22×40 with a 16px knob. It was 18×32, which is small for a thumb on a phone
 * — and this control is now the shape most settings take, so it carries more
 * of the drawer than it did when it only served the notification filters.
 *
 * The knob needs an explicit `left-0` origin — without it the absolutely-
 * positioned span keeps its static offset and the translate lands outside the
 * track. Offsets are hand-computed from those three numbers: 3px of inset on
 * each side, so the lit position is 40 − 16 − 3. */
export default function Switch({ checked, onChange, disabled, label }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-[22px] w-10 flex-none rounded-full transition-colors duration-200 ${
        checked ? 'bg-phosphor/60' : 'bg-white/10'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <span
        className={`absolute left-0 top-[3px] h-4 w-4 rounded-full bg-slate-100 shadow transition-transform duration-200 ${
          checked ? 'translate-x-[21px]' : 'translate-x-[3px]'
        }`}
      />
    </button>
  )
}
