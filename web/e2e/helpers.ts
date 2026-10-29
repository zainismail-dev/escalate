import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, request } from "@playwright/test";

/** DEMO_E2E=1: the static live demo build (NEXT_PUBLIC_DEMO_STATIC=true). There is no API. */
export const DEMO = process.env.DEMO_E2E === "1";

export const API_URL = process.env.API_URL || "http://localhost:8000";
const WEB_URL = process.env.WEB_URL || "http://localhost:3000";

/** API calls from tests behave like the web app: its Origin plus the anti-CSRF header. */
export const apiContext = () =>
  request.newContext({ extraHTTPHeaders: { Origin: new URL(WEB_URL).origin, "X-Escalate-Request": "1" } });

export interface DemoCase {
  id: string;
  country: string;
  waiting_for: string | null;
  pending_draft?: { id: number };
}

/** Demo cases by country (seeded by global setup). */
export async function demoCases(): Promise<Record<string, DemoCase>> {
  if (DEMO) return byCountry(JSON.parse(readFileSync(join(process.cwd(), "src/demo/list.json"), "utf8")));
  const ctx = await apiContext();
  const rows: DemoCase[] = await (await ctx.get(`${API_URL}/cases`)).json();
  await ctx.dispose();
  return byCountry(rows);
}

function byCountry(rows: DemoCase[]): Record<string, DemoCase> {
  const out: Record<string, DemoCase> = {};
  for (const r of rows) out[r.country] ??= r; // newest first
  return out;
}

export async function draftId(caseId: string): Promise<string> {
  return (await pendingDraft(caseId)).id;
}

export async function pendingDraft(caseId: string): Promise<{ id: string; recipient: string | null }> {
  const ctx = await apiContext();
  const c = await (await ctx.get(`${API_URL}/cases/${caseId}`)).json();
  await ctx.dispose();
  return c.pending_draft;
}

/** Wait until skeletons are gone. */
export async function settled(page: Page) {
  await expect(page.getByTestId("skeleton")).toHaveCount(0, { timeout: 15_000 });
}
