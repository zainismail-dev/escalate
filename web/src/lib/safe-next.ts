/** Where to go after sign-in. `next` comes from the URL (or sessionStorage, which the URL
 * filled), so it is attacker-controlled: only a path on this site is ever followed.
 *
 * Browsers "fix" a lot before navigating: `\` becomes `/`, and tabs and newlines are dropped,
 * so `/\evil.example`, `/%09/evil.example` and `/\\evil.example` all end up on another host.
 * Anything with a backslash, whitespace or a control character is refused outright, and what
 * is left must still resolve to this origin. */
export const DEFAULT_NEXT = "/cases";

const UNSAFE = /[\\\s\u0000-\u001f\u007f-\u009f]/;

// Only the path is ever returned, so any origin works for the check during prerendering.
const fallbackOrigin = () =>
  typeof window === "undefined" ? "https://escalate.invalid" : window.location.origin;

export function safeNext(next: string | null | undefined, origin = fallbackOrigin()): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) return DEFAULT_NEXT;
  let decoded = next;
  try {
    decoded = decodeURIComponent(next);
  } catch {
    return DEFAULT_NEXT;
  }
  if (UNSAFE.test(next) || UNSAFE.test(decoded) || decoded.startsWith("//")) return DEFAULT_NEXT;
  let url: URL;
  try {
    url = new URL(next, origin);
  } catch {
    return DEFAULT_NEXT;
  }
  if (url.origin !== new URL(origin).origin) return DEFAULT_NEXT;
  return url.pathname + url.search + url.hash;
}
