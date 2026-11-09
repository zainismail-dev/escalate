/** Errors whose wording differs in the hosted beta (no `make up`, no Settings page for the AI). */
const HOSTED_BODIES = ["offline_api", "ai_misconfigured"];

export function errorBodyKey(kind: string, hosted: boolean): string {
  return hosted && HOSTED_BODIES.includes(kind) ? `${kind}.hostedBody` : `${kind}.body`;
}

/** Review-page copy about sending. The hosted beta never sends (the user sends from their own
 * mailbox), so there the button says "Approve", not "Approve & send". */
const HOSTED_REVIEW = ["decision.title", "decision.body", "decision.approve", "confirm.title", "confirm.body", "confirm.cta"];

export function reviewKey(key: string, hosted: boolean): string {
  if (!hosted || !HOSTED_REVIEW.includes(key)) return key;
  const [group, name] = key.split(".");
  return `${group}.hosted.${name}`;
}
