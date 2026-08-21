/** Compile-time exhaustiveness check for a discriminated union.
 *
 * Put it in the `default` branch of a switch: adding a variant without handling
 * it stops type-checking, instead of falling through silently at runtime. The
 * runtime body is the fallback for a payload that violates the type — which,
 * over a WebSocket, is a real possibility rather than a theoretical one. */
export function assertNever(value: never): void {
  console.warn('unhandled variant', value)
}
