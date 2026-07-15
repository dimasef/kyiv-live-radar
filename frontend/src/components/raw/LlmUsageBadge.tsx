/** Dev-only "LLM" tag with token/cost detail — shown when the fallback was
 * called for this message, whether or not it recovered a district. */
export default function LlmUsageBadge({
  inputTokens,
  outputTokens,
  costUsd,
}: {
  inputTokens: number | null
  outputTokens: number | null
  costUsd: number | null
}) {
  const detail =
    inputTokens != null && outputTokens != null && costUsd != null
      ? `${inputTokens}+${outputTokens}t · $${costUsd.toFixed(4)}`
      : null

  return (
    <span
      className="flex items-center gap-1 rounded bg-violet-400/15 px-1 py-0.5 font-mono text-[9px] font-semibold tracking-tight text-violet-300"
      title={detail ? `${inputTokens} input + ${outputTokens} output tokens, $${costUsd?.toFixed(6)}` : undefined}
    >
      LLM
      {detail && <span className="opacity-70">{detail}</span>}
    </span>
  )
}
