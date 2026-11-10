import { defineConfig, devices } from "@playwright/test";

// End-to-end tests (Affan — Sprint 0 set-up, Sprint 1 join → upload).
//
// They run against a stack that is already up — locally `docker compose up` then
// `docker compose exec backend python -m app.cli seed-demo`; in CI the e2e workflow does the same.
// E2E_BASE_URL points at the frontend, E2E_API_URL at the backend.
export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  timeout: 90_000, // extraction of the planted SRS runs in the worker
  expect: { timeout: 15_000 },
  fullyParallel: false, // the join → upload flow shares one demo workspace
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
