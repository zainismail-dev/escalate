import path from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { API_URL, apiContext, demoCases, draftId, settled } from "./helpers";

/**
 * Screenshots of every page for the README: `make screenshots` (needs E2E_RESET=1 and demo
 * mode on the API, so approving the demo letter sends nothing).
 */
const OUT = path.resolve(__dirname, "../../docs/screenshots");
const shot = (page: Page, name: string, fullPage = true) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage });

test.describe.configure({ mode: "serial" });

test("landing", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Rs 64,500").first()).toBeVisible();
  await shot(page, "01-landing");
});

test("my cases", async ({ page }) => {
  await page.goto("/cases");
  await settled(page);
  await shot(page, "02-my-cases");
});

test("new case wizard", async ({ page }) => {
  await page.goto("/cases/new");
  await settled(page);
  await page.getByTestId("country-select").selectOption("BR");
  await shot(page, "03-new-case-where");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Tell us what happened").fill(
    "I ordered running shoes online (order SH-2291) and they arrived in the wrong size. The shop refuses to exchange them.",
  );
  await shot(page, "04-new-case-what");
  await page.getByRole("button", { name: "Next" }).click();
  await page.locator("#evidence").setInputFiles({
    name: "order-confirmation.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Order SH-2291\nRunning shoes, size 42\nTotal: BRL 389,90\n"),
  });
  await expect(page.getByText("order-confirmation.txt")).toBeVisible();
  await shot(page, "05-new-case-evidence");
  // No AI model in this environment: the "model offline, nothing was sent" state.
  await page.getByTestId("read-evidence").click();
  await expect(page.getByTestId("error-model_offline")).toBeVisible({ timeout: 30_000 });
  await shot(page, "06-state-model-offline");
});

test("missing facts with why we ask", async ({ page }) => {
  const { PK } = await demoCases();
  // Shown with a stubbed pending question list: the demo case already has every fact.
  await page.route(`${API_URL}/cases/${PK.id}`, async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.waiting_for = "questions";
    body.pending = { type: "questions", missing: ["seller_address", "buyer_address", "last_promise_on"] };
    await route.fulfill({ response: res, json: body });
  });
  await page.goto(`/cases/${PK.id}/questions`);
  await settled(page);
  await page.getByLabel("Seller's postal address").fill("Shop 12, Example Market");
  await shot(page, "07-missing-facts");
});

test("case dashboard", async ({ page }) => {
  const { PK } = await demoCases();
  await page.goto(`/cases/${PK.id}`);
  await settled(page);
  await shot(page, "08-case-dashboard");
});

test("review draft", async ({ page }) => {
  const { PK, US } = await demoCases();
  await page.goto(`/cases/${PK.id}/review`);
  await settled(page);
  await shot(page, "09-review-draft");
  await page.goto(`/cases/${US.id}/review`);
  await settled(page);
  await shot(page, "11-review-blank-to-fill");
});

test("draft blocked by fact check", async ({ page }) => {
  const { GB } = await demoCases();
  const id = await draftId(GB.id);
  const ctx = await apiContext();
  const msg = await (await ctx.get(`${API_URL}/messages/${id}/review`)).json();
  // An amount that is not in the evidence (the evidence says 39.99).
  const body = msg.message.body.replace("\n\n", "\n\nYou have charged me 49.99 every month since then.\n\n");
  await ctx.put(`${API_URL}/messages/${id}`, { data: { body } });
  await page.goto(`/cases/${GB.id}/review`);
  await settled(page);
  await expect(page.getByTestId("fact-check-blocked")).toBeVisible();
  await shot(page, "12-state-fact-check-blocked");
  await ctx.put(`${API_URL}/messages/${id}`, { data: { body: msg.message.body } });
  await ctx.dispose();
});

test("urgent scam checklist", async ({ page }) => {
  const { IN } = await demoCases();
  await page.goto(`/cases/${IN.id}/urgent`);
  await settled(page);
  await page.getByTestId("urgent-steps").getByRole("checkbox").first().check();
  await shot(page, "13-scam-urgent-checklist");
});

test("log a reply", async ({ page }) => {
  const { GB } = await demoCases();
  // Approve the demo letter (DEMO_MODE: nothing leaves the machine) so the case waits for a reply.
  const ctx = await apiContext();
  const ok = await ctx.post(`${API_URL}/messages/${await draftId(GB.id)}/approve`, { data: { confirm: true } });
  expect(ok.ok()).toBeTruthy();
  await ctx.dispose();
  await page.goto(`/cases/${GB.id}/reply`);
  await settled(page);
  await page.getByLabel("Paste their reply").fill(
    "Thanks for your message. We can cancel your membership once you visit the club in person. Refunds are not possible.",
  );
  await shot(page, "14-log-reply");
  // The verdict needs an AI model; show it with a stubbed answer.
  await page.route(`${API_URL}/cases/${GB.id}/replies`, (route) =>
    route.fulfill({
      json: {
        case_id: GB.id,
        waiting_for: "approve_draft",
        pending: null,
        warnings: [],
        verdict: "refused",
        reason: "They will only cancel in person and refuse any refund, so nothing you asked for was offered.",
        promise: null,
        promise_date: null,
        condition: "visit the club in person",
      },
    }),
  );
  await page.getByRole("button", { name: "Judge this reply" }).click();
  await expect(page.getByTestId("verdict-card")).toBeVisible();
  await shot(page, "15-reply-verdict");
});

test("settings", async ({ page }) => {
  await page.goto("/settings");
  await settled(page);
  await shot(page, "16-settings");
});

test.describe("dark", () => {
  test.use({ colorScheme: "dark" });
  test("dark mode", async ({ page }) => {
    const { PK } = await demoCases();
    await page.goto(`/cases/${PK.id}`);
    await settled(page);
    await shot(page, "17-dark-dashboard");
    await page.goto(`/cases/${PK.id}/review`);
    await settled(page);
    await shot(page, "18-dark-review");
    await page.goto("/cases");
    await settled(page);
    await shot(page, "19-dark-my-cases");
  });
});

test.describe("mobile", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  test("mobile", async ({ page }) => {
    await page.goto("/cases");
    await settled(page);
    await shot(page, "20-mobile-cases", false);
    const { US } = await demoCases();
    await page.goto(`/cases/${US.id}/review`);
    await settled(page);
    await shot(page, "21-mobile-review", false);
  });
});

test("states: loading skeleton and empty", async ({ page }) => {
  const listCases = (url: URL) => url.href.startsWith(API_URL) && url.pathname === "/cases";
  await page.route(listCases, async (route) => {
    await new Promise((r) => setTimeout(r, 4000));
    await route.fallback();
  });
  await page.goto("/cases");
  await expect(page.getByTestId("skeleton")).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "22-state-loading.png") });
  await page.unroute(listCases);
  await page.route(listCases, (route) => route.fulfill({ json: [] }));
  await page.goto("/cases");
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await shot(page, "23-state-empty");
});
