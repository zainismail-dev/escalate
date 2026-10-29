import { expect, type Page, test } from "@playwright/test";
import { demoCases, settled } from "./helpers";

/**
 * The static live demo (NEXT_PUBLIC_DEMO_STATIC=true, DEMO_E2E=1, no API running): sample data
 * only, every write explains itself, and the browser never requests anything but the app.
 */
const WEB = new URL(process.env.WEB_URL || "http://localhost:3000").origin;

/** Every request the page makes; anything off the app's own origin fails the test. */
function outbound(page: Page): string[] {
  const offsite: string[] = [];
  page.on("request", (r) => {
    const url = r.url();
    if (!url.startsWith("data:") && !url.startsWith("blob:") && new URL(url).origin !== WEB) offsite.push(url);
  });
  return offsite;
}

test("no request ever leaves the app, on any page", async ({ page }) => {
  const offsite = outbound(page);
  const { PK, IN, GB, US } = await demoCases();
  const paths = [
    "/",
    "/cases",
    "/cases/new",
    "/settings",
    `/cases/${PK.id}`,
    `/cases/${PK.id}/reply`,
    `/cases/${US.id}`,
    `/cases/${US.id}/review`,
    `/cases/${GB.id}/review`,
    `/cases/${IN.id}`,
    `/cases/${IN.id}/urgent`,
  ];
  for (const path of paths) {
    await page.goto(path);
    await settled(page);
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("demo-banner")).toHaveText(/Live demo · sample data · nothing is sent/);
    await expect(page.locator("[data-testid^=error-]")).toHaveCount(0);
  }
  expect(offsite).toEqual([]);
});

test("my cases shows the four sample cases", async ({ page }) => {
  await page.goto("/cases");
  await settled(page);
  await expect(page.getByTestId("case-card")).toHaveCount(4);
});

test("approve opens the demo dialog; nothing is sent", async ({ page }) => {
  const offsite = outbound(page);
  const { GB } = await demoCases();
  await page.goto(`/cases/${GB.id}/review`);
  await settled(page);
  await page.getByTestId("recipient-checkbox").click();
  await page.getByTestId("approve").click();
  // The real confirmation step, then the demo's answer instead of a send.
  await page.getByTestId("confirm-approve").click();
  const dialog = page.getByTestId("demo-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("This is a live demo with sample data. Nothing is saved or sent.");
  await expect(dialog.getByRole("link", { name: /GitHub/ })).toHaveAttribute("href", "https://github.com/zainismail-dev/escalate");
  expect(offsite).toEqual([]);
});

test("PDF downloads and delete-all open the demo dialog", async ({ page }) => {
  const { PK } = await demoCases();
  await page.goto(`/cases/${PK.id}`);
  await settled(page);
  await page.getByRole("link", { name: /export|case file/i }).first().click();
  await expect(page.getByTestId("demo-dialog")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.goto("/settings");
  await settled(page);
  await page.getByRole("button", { name: /delete all/i }).first().click();
  const confirm = page.getByRole("dialog").getByRole("button", { name: /delete/i });
  if (await confirm.count()) await confirm.last().click();
  await expect(page.getByTestId("demo-dialog")).toBeVisible();
  await expect(page.getByText("All cases deleted.")).toHaveCount(0); // a refused write never claims success
  await page.keyboard.press("Escape");
  await page.mouse.wheel(0, 3000);
  await expect(page.getByTestId("demo-banner")).toBeInViewport(); // permanent: in the sticky header
});

test("the new case wizard walks through with sample inputs and ends in the demo", async ({ page }) => {
  const offsite = outbound(page);
  await page.goto("/cases/new");
  await settled(page);
  await expect(page.getByTestId("demo-sample")).toBeVisible();
  await page.getByRole("button", { name: /next/i }).click();
  await expect(page.locator("#description")).toHaveValue(/running shoes/);
  await page.getByRole("button", { name: /next/i }).click();
  await page.getByTestId("demo-sample-evidence").click();
  await expect(page.getByText("sample-receipt.png")).toBeVisible();
  await page.getByTestId("read-evidence").click();
  await expect(page.getByTestId("demo-end")).toContainText("Demo ends here");
  expect(offsite).toEqual([]);
});

test("a sample reply is judged without a model", async ({ page }) => {
  const { PK } = await demoCases();
  await page.goto(`/cases/${PK.id}/reply`);
  await settled(page);
  await expect(page.locator("#reply-text")).toHaveValue(/goodwill/);
  await page.getByRole("button", { name: /judge|check/i }).click();
  await expect(page.getByTestId("verdict-card")).toBeVisible();
});
