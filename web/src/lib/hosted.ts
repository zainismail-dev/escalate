/** The hosted, invite-only beta (NEXT_PUBLIC_DEPLOY_MODE=hosted, docs/DEPLOY_BETA.md): Google
 * sign-in with Supabase, the server's AI provider, and the user sends letters from their own
 * mailbox. Self-hosted and demo builds never set it, and drop the hosted code at build time.
 * The env checks are inline so the build can do that. */
export const HOSTED = process.env.NEXT_PUBLIC_DEPLOY_MODE === "hosted" && process.env.NEXT_PUBLIC_DEMO_STATIC !== "true";

/** Public by design: the project URL and its anon (publishable) key. Nothing else reaches the
 * browser (scripts/scan-bundle.mjs --hosted fails the build otherwise). */
export const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").replace(/\/$/, "");
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

/** Pages a signed-out visitor may see in the hosted beta. */
export const PUBLIC_PATHS = ["/", "/signin", "/auth/callback", "/privacy", "/terms"];

export const SIGNED_OUT_EVENT = "escalate:signed-out";
export const WAITLIST_EVENT = "escalate:waitlist";
export const CONSENT_EVENT = "escalate:consent";
export const WAKING_EVENT = "escalate:waking";
