/** Stands in for ./supabase-client.ts in every build except the hosted beta (next.config.ts
 * alias), so self-hosted and demo bundles carry no Supabase code. Never called there. */
import type { SupabaseClient } from "@supabase/supabase-js";

export function createClient(): SupabaseClient | null {
  return null;
}
