import { expect, test, type Browser, type Page } from "@playwright/test";

// Integration Checkpoint 1 (Affan — US-30, US-31, US-14): a developer joins with a code, writes a
// requirement in the composer, and gets the result card in its thread within 60 s, while a second
// browser with the map open shows the new node within 2 s of the post (NFR-32) — and its conflict
// edge, when the analysis found one. Needs `python -m app.cli seed-demo`. Without an LLM key the
// run closes with "Analysis could not finish", which still proves the card path end to end.

const PM = { email: "project.manager@demo.local", password: "demo-password-123" };
const MAP_LAG_MS = 2_000;

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function openDemoWorkspace(page: Page) {
  await page.getByLabel("Workspace", { exact: true }).selectOption({ label: "Demo Workspace" });
  await expect(page).toHaveURL(/\/w\/[0-9a-f-]+$/);
}

async function openDemoProject(page: Page) {
  await page.getByLabel("Project", { exact: true }).selectOption({ label: "Demo Project" });
  await expect(page).toHaveURL(/\/p\/[0-9a-f-]+$/);
}

async function newPage(browser: Browser) {
  return (await browser.newContext()).newPage();
}

test("CP1: join → compose → result card → every open map updates", async ({ browser }) => {
  // 1. The project manager creates a Developer code, then keeps the project's map open.
  const manager = await newPage(browser);
  await signIn(manager, PM.email, PM.password);
  await openDemoWorkspace(manager);
  await manager.getByRole("link", { name: "Members & roles" }).click();
  await manager.getByRole("tab", { name: "Join codes" }).click();
  await manager.getByLabel("Role", { exact: true }).selectOption({ label: "Developer" });
  await manager.getByRole("button", { name: "Create code" }).click();
  const code = (await manager.locator(".mono", { hasText: /^[2-9A-Z]{4}-[2-9A-Z]{4}$/ }).first().textContent())!.trim();
  await openDemoProject(manager);
  await manager.getByRole("link", { name: "Map", exact: true }).click();
  await expect(manager).toHaveURL(/\/map$/);
  await manager.getByRole("button", { name: "Table view" }).click();
  const mapRequirements = manager.getByRole("table", { name: /^Requirements/ });
  await expect(mapRequirements).toBeVisible();

  // 2. A new developer signs up with the code in another browser and opens the project.
  const developer = await newPage(browser);
  await developer.goto(`/signup?code=${code}`);
  await developer.getByLabel("Full name").fill("CP1 Developer");
  await developer.getByLabel("Work email").fill(`cp1-${Date.now()}@example.com`);
  await developer.getByLabel("Password").fill("correct-horse-battery-staple");
  await developer.getByRole("button", { name: /create account/i }).click();
  await expect(developer).toHaveURL(/\/w\/[0-9a-f-]+/);
  await openDemoProject(developer);

  // 3. They write an event-driven requirement that contradicts the planted 30-minute timeout.
  await developer.getByRole("button", { name: "+ New requirement" }).click();
  await developer.getByLabel("Trigger", { exact: true }).fill("the user is inactive for 5 minutes");
  await developer.getByLabel("System", { exact: true }).fill("The mobile app");
  await developer.getByLabel("Response", { exact: true }).fill("shall log the user out.");
  const [response] = await Promise.all([
    developer.waitForResponse((r) => r.request().method() === "POST" && /\/projects\/[^/]+\/requirements$/.test(r.url())),
    developer.getByRole("button", { name: /propose requirement/i }).click(),
  ]);
  const postedAt = Date.now(); // the post's transaction has committed by the time it answers
  expect(response.status()).toBe(201);
  const posted = await response.json();
  const label: string = posted.requirement.source_req_id;
  expect(label).toMatch(/^REQ-\d+$/);

  // 4. The manager's map shows the new requirement within 2 s of the post's commit.
  await expect(mapRequirements.getByRole("button", { name: label, exact: true })).toBeVisible({ timeout: MAP_LAG_MS });
  test.info().annotations.push({ type: "map delta lag", description: `${Date.now() - postedAt} ms` });

  // 5. The result card arrives in the post's thread within 60 s.
  await expect(developer).toHaveURL(/\/channels\/[0-9a-f-]+/);
  const post = developer.getByRole("article").filter({ hasText: `${label} · Requirement` });
  await post.getByRole("button", { name: /reply|replies|Reply in thread/ }).click({ timeout: 60_000 });
  const card = developer.getByRole("log", { name: "Thread messages" }).getByRole("region", { name: "Analysis result" });
  await expect(card.locator("header")).toContainText(/\d+ s$/, { timeout: 60_000 });
  const cardText = (await card.textContent()) ?? "";
  test.info().annotations.push({ type: "result card", description: cardText.slice(0, 200) });

  // 6. Each conflict on the card is on the manager's map as well: the delta precedes the card.
  const relationships = manager.getByRole("table", { name: /^Relationships/ });
  for (const [, other] of cardText.matchAll(/Conflicting with (REQ-\d+)/g)) {
    await expect(relationships.getByText(`${label} conflicts with ${other}`).first()).toBeVisible({
      timeout: MAP_LAG_MS,
    });
  }
});
