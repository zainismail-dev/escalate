/** Where a long email address may wrap: before the "@" and after each ".", so it breaks
 * between its parts ("refunds.department" / "@brightmart" / ".example") instead of mid-word.
 * `wrap-anywhere` (overflow-wrap: anywhere) stays as the last resort for one very long part. */
export function emailBreakParts(address: string): string[] {
  const parts: string[] = [];
  let current = "";
  for (const ch of address) {
    if (ch === "@" && current) {
      parts.push(current);
      current = "";
    }
    current += ch;
    if (ch === ".") {
      parts.push(current);
      current = "";
    }
  }
  if (current) parts.push(current);
  return parts;
}
