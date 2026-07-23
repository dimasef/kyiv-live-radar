import { ClampText } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

const long =
  'Зафіксовано велику групу ударних БпЛА на підльоті до столиці з південно-східного напрямку. ' +
  'Ціль рухається курсом на центральні райони; ППО веде роботу. Перебувайте в укриттях до відбою. ' +
  'Не публікуйте фото та відео роботи протиповітряної оборони.'

export const Short = () => (
  <Stage>
    <div style={{ width: 260 }}>
      <ClampText text="Шахед над Троєщиною, курс південно-західний." className="text-xs text-slate-300" />
    </div>
  </Stage>
)
export const Clamped = () => (
  <Stage>
    <div style={{ width: 260 }}>
      <ClampText text={long} className="text-xs leading-snug text-slate-300" />
    </div>
  </Stage>
)
