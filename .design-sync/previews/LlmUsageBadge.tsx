import { LlmUsageBadge } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

export const WithDetail = () => <Stage><LlmUsageBadge inputTokens={1240} outputTokens={95} costUsd={0.0021} /></Stage>
export const TagOnly = () => <Stage><LlmUsageBadge inputTokens={null} outputTokens={null} costUsd={null} /></Stage>
