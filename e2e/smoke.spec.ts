import { expect, test } from "@playwright/test";

// Smoke (Sprint 0): the app is served, the API answers, and a signed-out visitor lands on sign-in.

const API = process.env.E2E_API_URL ?? "http://localhost:8000";

test("the API is healthy", async ({ request }) => {
  const response = await request.get(`${API}/health`);
  expect(response.ok()).toBeTruthy();
});

test("a signed-out visitor is sent to sign in", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});

test("the component kit renders", async ({ page }) => {
  await page.goto("/kit");
  await expect(page.getByRole("heading", { name: "Component kit" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Join codes" })).toBeVisible();
});
