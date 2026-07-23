import { LlmTriageBadge } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

export const Localized = () => <Stage><LlmTriageBadge category="localized" surface={false} /></Stage>
export const CitywideSurface = () => <Stage><LlmTriageBadge category="citywide" surface={true} /></Stage>
export const Directional = () => <Stage><LlmTriageBadge category="directional" surface={true} /></Stage>
export const Forecast = () => <Stage><LlmTriageBadge category="forecast" surface={false} /></Stage>
export const Noise = () => <Stage><LlmTriageBadge category="noise" surface={false} /></Stage>
