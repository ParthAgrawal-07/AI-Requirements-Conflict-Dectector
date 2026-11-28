import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// Sprint 4 merge rules end to end (Affan — US-33, US-35, FR-98): a developer proposes a change,
// cannot approve or merge it; the owner approves; an edit dismisses that approval; the owner
// approves the new revision and merges; a competing request then shows "needs update". Needs
// `python -m app.cli seed-demo` and a worker (the consequence checks run there). The requirement
// is posted fresh through the API so the run never depends on earlier runs.

const API = `${process.env.E2E_API_URL ?? "http://localhost:8000"}/api/v1`;
const PASSWORD = "demo-password-123";
const OWNER = "business.analyst@demo.local"; // posts the requirement, so owns it; may merge
const PROPOSER = "developer@demo.local"; // may open change requests, not merge
const COMPETITOR = "qa.engineer@demo.local";
const CHECKS_MS = 60_000;

async function token(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post(`${API}/auth/login`, { form: { username: email, password: PASSWORD } });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token;
}

const bearer = (value: string) => ({ Authorization: `Bearer ${value}` });

async function demoProject(request: APIRequestContext, auth: string) {
  const workspaces = await (await request.get(`${API}/workspaces`, { headers: bearer(auth) })).json();
  const workspace = workspaces.find((w: { name: string }) => w.name === "Demo Workspace");
  const projects = await (await request.get(`${API}/workspaces/${workspace.id}/projects`, { headers: bearer(auth) })).json();
  const project = projects.items.find((p: { name: string }) => p.name === "Demo Project");
  return { workspaceId: workspace.id as string, projectId: project.id as string };
}

/** The access token lives in memory only (US-19), so every full page load signs in again; the
 *  login page sends the browser back to where it was going. */
async function visit(page: Page, email: string, path: string) {
  await page.goto(path);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function open(browser: Browser, email: string, path: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await visit(page, email, path);
  return page;
}

/** The Checks tab until the report for the current revision is in (the worker writes it; the
 *  change_request.checked event refreshes the tab). An earlier revision's report shows as stale. */
async function waitForChecks(page: Page) {
  await page.getByRole("tab", { name: /^Checks/ }).click();
  await expect(page.getByRole("region", { name: "Findings delta" })).toBeVisible({ timeout: CHECKS_MS });
  await expect(page.getByText("These results are out of date.")).toHaveCount(0, { timeout: CHECKS_MS });
  await page.getByRole("tab", { name: /^Conversation/ }).click();
}

async function approve(page: Page) {
  const form = page.getByRole("form", { name: "Your review" });
  await form.getByRole("radio", { name: "Approve" }).check();
  await form.getByRole("button", { name: "Send review" }).click();
  await expect(page.getByText(/Review sent on revision/)).toBeVisible();
}

test("change request: no self-approval, merge permission, edits dismiss approvals, needs update", async ({
  browser,
  request,
}) => {
  const ownerToken = await token(request, OWNER);
  const { workspaceId, projectId } = await demoProject(request, ownerToken);
  const base = `/w/${workspaceId}/p/${projectId}`;
  const stamp = Date.now();
  const posted = await request.post(`${API}/projects/${projectId}/requirements`, {
    headers: bearer(ownerToken),
    data: {
      fields: {
        template: "event_driven",
        slots: { trigger: `the user is inactive for 30 minutes (run ${stamp})`, system: "web app", response: "end the session" },
        type: "functional",
        priority: "must",
        tags: [],
        acceptance_criteria: [],
      },
    },
  });
  expect(posted.status()).toBe(201);
  const requirement = (await posted.json()).requirement;
  const label: string = requirement.source_req_id;

  // 1. The developer proposes a change from the change editor.
  const proposer = await open(browser, PROPOSER, `${base}/changes/new?requirement=${requirement.requirement_id}`);
  const text = proposer.getByLabel("Proposed text");
  await text.fill((await text.inputValue()).replace("30 minutes", "10 minutes"));
  await expect(proposer.getByLabel("Your changes").locator("ins")).toContainText("10");
  await proposer.getByLabel("Reason (required)").fill("Audit finding A-17: idle sessions end within 10 minutes");
  await proposer.getByRole("button", { name: "Open change request" }).click();
  await expect(proposer).toHaveURL(/\/changes\/[0-9a-f-]+$/);
  const changeId = proposer.url().split("/").pop()!;
  const crPath = `${base}/changes/${changeId}`;

  // 2. No self-approval: no review form in the UI, and the API refuses it.
  await expect(proposer.getByRole("heading", { name: new RegExp(`Change ${label}`) })).toBeVisible();
  await expect(proposer.getByRole("form", { name: "Your review" })).toHaveCount(0);
  const proposerToken = await token(request, PROPOSER);
  const selfApproval = await request.post(`${API}/change-requests/${changeId}/reviews`, {
    headers: bearer(proposerToken),
    data: { decision: "approve" },
  });
  expect(selfApproval.status()).toBe(403);
  expect((await selfApproval.json()).error.code).toBe("self_approval");

  // 3. Merge permission: greyed out for the developer, refused by the API.
  const merge = proposer.getByRole("button", { name: "Merge into baseline" });
  await expect(merge).toBeDisabled();
  await expect(merge).toHaveAttribute("title", /cannot merge/);
  const devMerge = await request.post(`${API}/change-requests/${changeId}/merge`, { headers: bearer(proposerToken), data: {} });
  expect(devMerge.status()).toBe(403);

  // 4. The owner approves revision 1.
  const owner = await open(browser, OWNER, crPath);
  await waitForChecks(owner);
  await approve(owner);

  // 5. A competing request on the same requirement, opened by someone else.
  const competitorToken = await token(request, COMPETITOR);
  const competing = await request.post(`${API}/requirements/${requirement.requirement_id}/change-requests`, {
    headers: bearer(competitorToken),
    data: { proposed_body: `When the user is inactive for 20 minutes (run ${stamp}), the web app shall end the session.`, reason: "Kiosks need longer" },
  });
  expect(competing.status()).toBe(201);
  const competingId = (await competing.json()).id;

  // 6. FR-98: the proposer edits; the owner's approval is dismissed and merge is blocked again.
  await visit(proposer, PROPOSER, crPath);
  await proposer.getByRole("button", { name: "Edit proposal" }).click();
  const edit = proposer.getByRole("form", { name: "Edit the proposal" });
  const editText = edit.getByLabel("Proposed text");
  await editText.fill((await editText.inputValue()).replace("10 minutes", "15 minutes"));
  await edit.getByRole("button", { name: "Save new revision" }).click();
  await expect(proposer.getByText(/is now revision 2/)).toBeVisible();

  await visit(owner, OWNER, crPath);
  await expect(owner.getByText(/dismissed: the proposal or its base changed since/)).toBeVisible();
  const conditions = owner.getByRole("list", { name: "Agreement conditions" });
  await expect(conditions).toContainText(/0 of 1 required approval/);
  await expect(owner.getByRole("button", { name: "Merge into baseline" })).toBeDisabled();

  // 7. The owner approves revision 2 once its checks are in, and merges.
  await waitForChecks(owner);
  await approve(owner);
  await visit(owner, OWNER, crPath);
  const ownerMerge = owner.getByRole("button", { name: "Merge into baseline" });
  await expect(ownerMerge).toBeEnabled();
  await ownerMerge.click();
  await expect(owner.getByText(`Merged: ${label} is now v2.`)).toBeVisible();

  // 8. The competing request now needs an update and cannot merge on the old base.
  await visit(owner, OWNER, `${base}/changes/${competingId}`);
  await expect(owner.getByText(new RegExp(`${label} changed to v2 after this request was written against v1`))).toBeVisible();
  await owner.getByRole("tab", { name: "Files changed" }).click();
  await expect(owner.getByText("Changed underneath: v1 → v2")).toBeVisible();
  const stale = await request.post(`${API}/change-requests/${competingId}/merge`, { headers: bearer(ownerToken), data: {} });
  expect(stale.status()).toBe(409);
  const unmet = (await stale.json()).error.details.map((d: { code: string }) => d.code);
  expect(unmet).toContain("needs_update");
});

// Marking a requirement protected arrives with US-18 (Sprint 6); until then the compliance rule is
// covered by backend/tests/security/test_merge_rules.py.
test.fixme("change request on a protected requirement needs a compliance approval", async () => {});
