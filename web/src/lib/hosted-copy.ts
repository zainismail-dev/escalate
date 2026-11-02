/** Errors whose wording differs in the hosted beta (no `make up`, no Settings page for the AI). */
const HOSTED_BODIES = ["offline_api", "ai_misconfigured"];

export function errorBodyKey(kind: string, hosted: boolean): string {
  return hosted && HOSTED_BODIES.includes(kind) ? `${kind}.hostedBody` : `${kind}.body`;
}
