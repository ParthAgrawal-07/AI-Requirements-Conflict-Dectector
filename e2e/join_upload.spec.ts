import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// Sprint 1 exit check (Affan): a project manager creates a code, a developer signs up with it,
// gets the Developer role, uploads the planted SRS and sees its requirements with printed IDs.
// Needs `python -m app.cli seed-demo` (Demo Workspace, Demo Project, one member per role).

const PM = { email: "project.manager@demo.local", password: "demo-password-123" };
const PLANTED_SRS = path.resolve(__dirname, "../eval/benchmark_v2/srs_planted.docx");

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

test("create code → join → upload → see requirements", async ({ browser }) => {
  // 1. The project manager creates a Developer code for the workspace.
  const manager = await (await browser.newContext()).newPage();
  await signIn(manager, PM.email, PM.password);
  await openDemoWorkspace(manager);
  await manager.getByRole("link", { name: "Members & roles" }).click();
  await expect(manager).toHaveURL(/\/members$/);
  await manager.getByRole("tab", { name: "Join codes" }).click();
  await manager.getByLabel("Role", { exact: true }).selectOption({ label: "Developer" });
  await manager.getByRole("button", { name: "Create code" }).click();
  const code = (await manager.locator(".mono", { hasText: /^[2-9A-Z]{4}-[2-9A-Z]{4}$/ }).first().textContent())!.trim();
  expect(code).toMatch(/^[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}$/);

  // 2. A new developer signs up with it, in a separate browser context (no shared session).
  const developer = await (await browser.newContext()).newPage();
  const email = `dev-${Date.now()}@example.com`;
  await developer.goto(`/signup?code=${code}`);
  await developer.getByLabel("Full name").fill("E2E Developer");
  await developer.getByLabel("Work email").fill(email);
  await developer.getByLabel("Password").fill("correct-horse-battery-staple");
  await developer.getByRole("button", { name: /create account/i }).click();
  await expect(developer).toHaveURL(/\/w\/[0-9a-f-]+/);

  // 3. They open the demo project and upload the planted SRS as proposals.
  await developer.getByLabel("Project", { exact: true }).selectOption({ label: "Demo Project" });
  await expect(developer).toHaveURL(/\/p\/[0-9a-f-]+$/); // the switch has landed on the project
  await developer.getByRole("link", { name: "Requirements", exact: true }).click();
  await expect(developer).toHaveURL(/\/requirements$/);
  await developer.getByRole("button", { name: "Upload SRS" }).click();
  await developer.getByLabel("Document", { exact: true }).setInputFiles(PLANTED_SRS);
  // Developers cannot import a baseline: the option is not offered (US-01, permission-driven).
  await expect(developer.getByLabel(/Baseline/)).toHaveCount(0);
  await developer.getByRole("button", { name: "Upload", exact: true }).click();

  // 4. Extraction finishes and the requirements appear with their printed IDs.
  // .first(): the demo project may already hold earlier uploads of the same SRS (re-runs, retries).
  await expect(developer.getByRole("cell", { name: "REQ-014" }).first()).toBeVisible({
    timeout: 60_000,
  });
  await expect(developer.getByText(/inactive|unsuccessful login attempt/).first()).toBeVisible();

  // 5. The code's use was counted on the manager's screen.
  // Switching tabs remounts the list, which always refetches. (A reload would sign the manager
  // out: the token lives in memory only, US-19.)
  await manager.getByRole("tab", { name: "Roles" }).click();
  await manager.getByRole("tab", { name: "Join codes" }).click();
  await expect(manager.getByRole("row", { name: new RegExp(code.slice(-4)) })).toContainText("1 /");
});

test("a used-up or wrong code is refused with one generic message", async ({ page }) => {
  await page.goto("/signup?code=ZZZZ-ZZZZ");
  await page.getByLabel("Full name").fill("Nobody");
  await page.getByLabel("Work email").fill(`nobody-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("alert")).toContainText("We could not create an account");
});
