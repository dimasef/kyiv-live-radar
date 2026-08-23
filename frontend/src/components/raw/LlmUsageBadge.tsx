/** Dev-only "LLM" tag with token/cost detail — shown when a call was ATTEMPTED
 * for this message, whether or not it recovered a district.
 *
 * Missing token/cost means the call never returned (timeout, network, API
 * error), so it is called out rather than left as a bare tag: on 2026-08-23 the
 * type classifier's timeout was firing regularly and, because nothing recorded
 * it, the losses read as "no call was made". */
export default function LlmUsageBadge({
  inputTokens,
  outputTokens,
  costUsd,
}: {
  // `| undefined` as well as `| null`: these are optional in the generated API
  // types (the server defaults them to None, so they aren't schema-required).
  inputTokens: number | null | undefined
  outputTokens: number | null | undefined
  costUsd: number | null | undefined
}) {
  const completed =
    inputTokens != null && outputTokens != null && costUsd != null

  if (!completed) {
    return (
      <span
        className="flex items-center gap-1 rounded bg-amber-400/15 px-1 py-0.5 font-mono text-[9px] font-semibold tracking-tight text-amber-300"
        title="Виклик LLM не завершився — таймаут або помилка API. Нічого не витрачено."
      >
        LLM
        <span className="opacity-70">без відповіді</span>
      </span>
    )
  }

  return (
    <span
      className="flex items-center gap-1 rounded bg-violet-400/15 px-1 py-0.5 font-mono text-[9px] font-semibold tracking-tight text-violet-300"
      title={`${inputTokens} input + ${outputTokens} output tokens, $${costUsd.toFixed(6)}`}
    >
      LLM
      <span className="opacity-70">
        {inputTokens}+{outputTokens}t · ${costUsd.toFixed(4)}
      </span>
    </span>
  )
}
