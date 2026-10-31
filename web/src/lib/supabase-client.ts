/** The hosted beta's Supabase browser client. Only the hosted build bundles this file (the
 * "escalate-supabase" alias in next.config.ts); other builds get ./supabase-disabled.ts. */
import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

export function createClient(url: string, anonKey: string): SupabaseClient | null {
  return createBrowserClient(url, anonKey, { auth: { flowType: "pkce", detectSessionInUrl: true } });
}
