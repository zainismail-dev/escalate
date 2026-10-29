import { API_URL, apiContext } from "./helpers";

export default async function globalSetup() {
  const ctx = await apiContext();
  const health = await ctx.get(`${API_URL}/health`);
  if (!health.ok()) throw new Error(`API not reachable at ${API_URL}`);
  const cases = await (await ctx.get(`${API_URL}/cases`)).json();
  if (process.env.E2E_RESET === "1") {
    await ctx.post(`${API_URL}/privacy/delete-all`, { data: { confirm: true } });
  }
  const countries = new Set((process.env.E2E_RESET === "1" ? [] : cases).map((c: { country: string }) => c.country));
  if (!["PK", "IN", "GB", "US"].every((c) => countries.has(c))) {
    const r = await ctx.post(`${API_URL}/demo/seed`);
    if (!r.ok()) throw new Error(`demo seed failed: ${r.status()} ${await r.text()}`);
  }
  await ctx.dispose();
}
