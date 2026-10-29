import { expect, type Page, request } from "@playwright/test";

export const API_URL = process.env.API_URL || "http://localhost:8000";
const WEB_URL = process.env.WEB_URL || "http://localhost:3000";

/** API calls from tests behave like the web app: its Origin plus the anti-CSRF header. */
export const apiContext = () =>
  request.newContext({ extraHTTPHeaders: { Origin: new URL(WEB_URL).origin, "X-Escalate-Request": "1" } });

export interface DemoCase {
  id: number;
  country: string;
  waiting_for: string | null;
  pending_draft?: { id: number };
}

/** Demo cases by country (seeded by global setup). */
export async function demoCases(): Promise<Record<string, DemoCase>> {
  const ctx = await apiContext();
  const rows: DemoCase[] = await (await ctx.get(`${API_URL}/cases`)).json();
  const out: Record<string, DemoCase> = {};
  for (const r of rows) out[r.country] ??= r; // newest first
  await ctx.dispose();
  return out;
}

export async function draftId(caseId: number): Promise<number> {
  const ctx = await apiContext();
  const c = await (await ctx.get(`${API_URL}/cases/${caseId}`)).json();
  await ctx.dispose();
  return c.pending_draft.id;
}

/** Wait until skeletons are gone. */
export async function settled(page: Page) {
  await expect(page.getByTestId("skeleton")).toHaveCount(0, { timeout: 15_000 });
}
