import { expect, test } from "@playwright/test";
import { demoCases, settled } from "./helpers";

test("landing: dark hero, ladder, sections", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Don't give up");
  await expect(page.getByTestId("hero-ladder").getByRole("listitem")).toHaveCount(4);
  await expect(page.getByText("Why this step?")).toBeVisible();
  // Intl formats each example in its own locale.
  await expect(page.getByText("Rs 64,500").first()).toBeVisible();
  await expect(page.getByText("89,90 €")).toBeVisible();
  await expect(page.getByText("$1,249", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Every country. Every currency." })).toBeVisible();
  await expect(page.getByText(/more languages are coming/i)).toHaveCount(1); // said once, small
  await expect(page.getByText(/every script|right-to-left|any language/i)).toHaveCount(0);
});

test("my cases: urgent first, titles, real next steps, 2-column grid", async ({ page }) => {
  await page.goto("/cases");
  await settled(page);
  const cards = page.getByTestId("case-card");
  await expect(cards).toHaveCount(4);
  await expect(cards.first()).toHaveAttribute("data-urgent", "true");
  await expect(cards.first().getByTestId("next-step")).toHaveText("Do the checklist");
  await expect(cards.first()).toContainText("Fake delivery SMS payment");
  const pk = cards.filter({ hasText: "Broken LED TV — refund refused" });
  await expect(pk).toContainText("BrightMart Electronics");
  await expect(pk.getByTestId("next-step")).toHaveText("Approve written demand to the seller");
  const amounts = await page.getByTestId("card-amount").allInnerTexts();
  expect(amounts.map((a) => a.replace(/\s/g, " ")).sort()).toEqual(["$1,249", "Rs 64,500", "£39.99", "₹18,000"].sort());
  // Two columns on desktop: the first two cards share a row.
  const [a, b] = [await cards.nth(0).boundingBox(), await cards.nth(1).boundingBox()];
  expect(Math.abs(a!.y - b!.y)).toBeLessThan(2);
  expect(b!.x).toBeGreaterThan(a!.x + a!.width - 1);
  await page.getByLabel("Filter by country").selectOption("GB");
  await expect(cards).toHaveCount(1);
  await expect(cards).toContainText("Gym still charging after cancelling");
});

test("review: verified facts highlighted, approve gated by confirm dialog", async ({ page }) => {
  const { PK } = await demoCases();
  await page.goto(`/cases/${PK.id}/review`);
  await settled(page);
  const letter = page.getByTestId("letter");
  await expect(letter.locator("mark.fact-mark").first()).toBeVisible();
  await expect(letter).toContainText("BM-48213");
  const approve = page.getByTestId("approve");
  await expect(approve).toBeEnabled();
  await approve.click();
  await expect(page.getByRole("dialog")).toContainText("Approve and send?");
  await page.getByRole("button", { name: "Cancel" }).click(); // never send in a smoke test
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("review: a blank keeps Approve disabled", async ({ page }) => {
  const { US } = await demoCases();
  await page.goto(`/cases/${US.id}/review`);
  await settled(page);
  await expect(page.getByTestId("letter").locator("[data-blank]")).toHaveCount(1);
  await expect(page.getByTestId("approve")).toBeDisabled();
  await expect(page.getByTestId("approve-why")).toContainText("Fill in 1 blank");
});

test("v0.1 is English-only: no language selectors anywhere", async ({ page }) => {
  const { PK } = await demoCases();
  for (const path of ["/", "/cases", "/cases/new", "/settings", `/cases/${PK.id}`, `/cases/${PK.id}/review`]) {
    await page.goto(path);
    await settled(page);
    await expect(page.getByLabel(/language/i), path).toHaveCount(0);
    await expect(page.getByRole("button", { name: /side by side/i }), path).toHaveCount(0);
  }
  await expect(page.getByTestId("letter")).toHaveAttribute("lang", "en");
});

test("scam: urgent checklist with never-share and recovery warnings", async ({ page }) => {
  const { IN } = await demoCases();
  await page.goto(`/cases/${IN.id}/urgent`);
  await settled(page);
  await expect(page.getByTestId("urgent-banner")).toBeVisible();
  await expect(page.getByTestId("urgent-steps").getByRole("checkbox")).toHaveCount(4);
  await expect(page.getByTestId("never-share")).toBeVisible();
  await expect(page.getByTestId("recovery-warning")).toBeVisible();
  await expect(page.getByTestId("urgent-done")).toBeDisabled();
});

test("new case: every country listed, honest pack badge", async ({ page }) => {
  await page.goto("/cases/new");
  await settled(page);
  const select = page.getByTestId("country-select");
  expect(await select.locator("option").count()).toBeGreaterThan(240);
  await select.selectOption("FR");
  await expect(page.getByTestId("country-summary")).toContainText("Generic route");
  await select.selectOption("PK");
  await expect(page.getByTestId("country-summary")).toContainText("Local pack");
});

test("settings: model, email, language, privacy", async ({ page }) => {
  await page.goto("/settings");
  await settled(page);
  for (const h of ["AI model", "Email", "Language and region", "Privacy"]) {
    await expect(page.getByRole("heading", { name: h })).toBeVisible();
  }
  await expect(page.getByLabel("App password")).toHaveAttribute("type", "password");
});
