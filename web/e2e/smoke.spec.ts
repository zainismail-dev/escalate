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
  await expect(page.getByText("$1,249.00")).toBeVisible();
  await expect(page.locator("[lang=ur][dir=rtl]")).toBeVisible();
});

test("my cases: needs-you cards, filters and mini ladders", async ({ page }) => {
  await page.goto("/cases");
  await settled(page);
  await expect(page.getByTestId("needs-you-card").first()).toBeVisible();
  const list = page.getByTestId("case-list");
  await expect(list.getByRole("listitem")).toHaveCount(4);
  await expect(list).toContainText("£39.99");
  await expect(list).toContainText("₹18,000");
  await page.getByLabel("Filter by country").selectOption("GB");
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await expect(list).toContainText("Generic route");
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

test("review: side-by-side preview in another letter language", async ({ page }) => {
  const { PK } = await demoCases();
  await page.goto(`/cases/${PK.id}/review`);
  await settled(page);
  await page.getByRole("button", { name: "Side by side" }).click();
  const preview = page.getByTestId("letter-preview");
  await expect(preview).toHaveAttribute("dir", "rtl");
  await expect(preview).toHaveAttribute("lang", "ur");
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
