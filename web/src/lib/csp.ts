import { API_URL } from "./api-url";
import { DEMO_STATIC } from "./demo-mode";
import { HOSTED, SUPABASE_URL } from "./hosted";

/** The page may talk to itself and, unless it is the static demo, the Escalate API (and, in the
 * hosted beta, Supabase Auth). */
export function contentSecurityPolicy(nonce: string, { dev = false, https = false } = {}): string {
  const supabase = HOSTED && SUPABASE_URL ? [new URL(SUPABASE_URL).origin] : [];
  const connect = ["'self'", ...(DEMO_STATIC ? [] : [new URL(API_URL).origin]), ...supabase, ...(dev ? ["ws:"] : [])];
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    // Dev only: hot reload injects <style> tags without a nonce (and a nonce would make
    // browsers ignore 'unsafe-inline'). Production builds are nonce-only.
    dev ? "style-src 'self' 'unsafe-inline'" : `style-src 'self' 'nonce-${nonce}'`,
    // React sets some styles as attributes (Radix positioning, progress widths). Attribute styles
    // cannot run script; scripts stay nonce-only.
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src ${connect.join(" ")}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(https ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
}
