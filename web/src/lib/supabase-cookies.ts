/** Cookie options for the Supabase session (SECURITY.md, "Session cookies"). The browser
 * client has to read its own session, so the cookie can't be httpOnly; it is Secure on https,
 * SameSite=Lax (never sent on cross-site subrequests) and expires after a week instead of
 * @supabase/ssr's default of 400 days. */
export const SESSION_MAX_AGE_S = 7 * 24 * 60 * 60;

export function sessionCookieOptions(protocol?: string) {
  const p = protocol ?? (typeof window === "undefined" ? "https:" : window.location.protocol);
  return {
    path: "/",
    sameSite: "lax" as const,
    secure: p === "https:",
    maxAge: SESSION_MAX_AGE_S,
  };
}
