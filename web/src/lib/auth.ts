/** Supabase Auth in the hosted beta (Google sign-in only). The session lives in the browser;
 * the API gets the short-lived access token as a bearer token on each request and never sets a
 * cookie. Other builds get a stub client (null) and never call Supabase. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { HOSTED, SUPABASE_ANON_KEY, SUPABASE_URL } from "./hosted";

let client: Promise<SupabaseClient | null> | null = null;

export function supabase(): Promise<SupabaseClient | null> {
  if (!HOSTED || typeof window === "undefined") return Promise.resolve(null);
  // A stub in other builds (next.config.ts alias): they carry no Supabase code at all.
  client ??= import("escalate-supabase").then((m) => m.createClient(SUPABASE_URL, SUPABASE_ANON_KEY));
  return client;
}

/** The current access token (refreshed by the client when it is about to expire), or null. */
export async function accessToken(): Promise<string | null> {
  const sb = await supabase();
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function signedInEmail(): Promise<string | null> {
  const sb = await supabase();
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session?.user.email ?? null;
}

export async function signInWithGoogle(): Promise<void> {
  const sb = await supabase();
  if (!sb) return;
  await sb.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: `${window.location.origin}/auth/callback` },
  });
}

export async function signOut(): Promise<void> {
  const sb = await supabase();
  await sb?.auth.signOut();
}

/** Calls `fn` whenever the user signs in or out; returns the unsubscribe function. */
export async function onAuthChange(fn: (email: string | null) => void): Promise<() => void> {
  const sb = await supabase();
  if (!sb) return () => {};
  const { data } = sb.auth.onAuthStateChange((_event, session) => fn(session?.user.email ?? null));
  return () => data.subscription.unsubscribe();
}
