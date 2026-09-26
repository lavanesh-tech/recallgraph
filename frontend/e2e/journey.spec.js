// End-to-end user journey through the real UI, API and database. Accounts are unique per run.
import { expect, test } from "@playwright/test";

const password = "e2e correct horse battery staple";

async function register(page) {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in" }).click();
  await page.getByRole("button", { name: /Need an account/ }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText(email)).toBeVisible();
  return email;
}

test("anonymous search always shows the official-data disclaimer", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Keywords").fill("air fryer");
  await page.getByRole("button", { name: "Search" }).click();

  await expect(page.getByText(/matching records/)).toBeVisible();
  await expect(page.getByRole("note")).toBeVisible();
});

test("register, save a product, check it and view alerts", async ({ page }) => {
  await register(page);

  await page.getByRole("link", { name: "My products" }).click();
  await page.getByLabel("Nickname").fill("E2E kitchen gadget");
  await page.getByLabel("Model").fill("E2E-ZZQX-000");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E kitchen gadget")).toBeVisible();

  await page.getByRole("button", { name: "Check recalls" }).click();
  // Either explained matches or the explicit "not safe" wording; never a silent "safe".
  await expect(
    page.getByText(/does not mean the product is safe|Why this matched/).first(),
  ).toBeVisible();

  await page.getByRole("link", { name: "Alerts" }).click();
  await expect(page.getByRole("heading", { name: "Recall Radar" })).toBeVisible();
  await expect(page.getByText(/unread of/)).toBeVisible();
});

test("signing out protects private pages", async ({ page }) => {
  await register(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("/inventory");

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("API responses carry security headers", async ({ request }) => {
  const response = await request.get("/api/v1/health");

  expect(response.ok()).toBeTruthy();
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
  expect(response.headers()["x-request-id"]).toBeTruthy();
});
