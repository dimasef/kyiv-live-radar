import { Switch } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

export const On = () => <Stage><Switch checked onChange={() => {}} label="Сповіщення про «шахеди»" /></Stage>
export const Off = () => <Stage><Switch checked={false} onChange={() => {}} label="Сповіщення про «шахеди»" /></Stage>
export const Disabled = () => <Stage><Switch checked disabled onChange={() => {}} label="Сповіщення вимкнені" /></Stage>
