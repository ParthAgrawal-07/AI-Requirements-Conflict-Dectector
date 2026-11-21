import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// Checkpoint 2 end to end (Affan — US-58, US-38, US-45, US-57, US-40): two owners post
// requirements that contradict each other in different words; the rule check finds it below the
// similarity threshold and opens an issue assigned to both; the AI suggests three resolutions;
// both owners mark a preference; the manager edits one and accepts it into a pre-filled change
// request; the decision owner approves; it merges; snapshot v1.1 is compared with v1.0.
//
// Needs `python -m app.cli seed-demo`, a worker and a model key on the stack (E2E_LLM=1): without
// one a requirement can never be approved (its single checks need the model) and suggestions
// stay pending, so the loop cannot run. Each run makes its own project, so earlier runs and the
// demo project never interfere; its similarity threshold is 0.95 so the AI never also classifies
// the pair and the rule finding is the only one.

const API = `${process.env.E2E_API_URL ?? "http://localhost:8000"}/api/v1`;
const PASSWORD = "demo-password-123";
const OWNER = "owner@demo.local"; // creates the project
const ANALYST = "business.analyst@demo.local"; // owns REQ A; may merge
const DEVELOPER = "developer@demo.local"; // owns REQ B
const MANAGER = "project.manager@demo.local"; // approves A and B, accepts a suggestion, freezes snapshots
const EMAIL_OF: Record<string, string> = {
  "Demo Business Analyst": ANALYST,
  "Demo Developer": DEVELOPER,
  "Demo Project Manager": MANAGER,
};
// Benchmark pair BT-02 (eval/benchmark_v2/below_threshold.csv): 0.743 alike, caught by numeric_limit.
const A_TEXT = "The session shall expire after 30 minutes of inactivity.";
const B_TEXT = "The session shall time out after 5 minutes.";
const AI_MS = 120_000;
const CHECKS_MS = 60_000;

test.skip(!process.env.E2E_LLM, "CP2 needs a model key on the stack (set E2E_LLM=1 once it has one)");

const bearer = (value: string) => ({ Authorization: `Bearer ${value}` });

async function token(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post(`${API}/auth/login`, { form: { username: email, password: PASSWORD } });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token;
}

async function call<T>(
  request: APIRequestContext,
  auth: string,
  method: "GET" | "POST" | "PUT" | "PATCH",
  path: string,
  data?: unknown,
): Promise<{ status: number; body: T }> {
  const response = await request.fetch(`${API}${path}`, { method, headers: bearer(auth), data });
  return { status: response.status(), body: await response.json() };
}

/** A fresh, active project in the demo workspace. */
async function cp2Project(request: APIRequestContext, auth: string) {
  const workspaces = (await call<{ id: string; name: string }[]>(request, auth, "GET", "/workspaces")).body;
  const workspaceId = workspaces.find((w) => w.name === "Demo Workspace")!.id;
  const created = await call<{ id: string }>(request, auth, "POST", `/workspaces/${workspaceId}/projects`, {
    name: `CP2 ${Date.now()}`,
    similarity_threshold: 0.95,
  });
  expect(created.status).toBe(201);
  const activated = await call<{ activated: boolean }>(request, auth, "PUT", `/projects/${created.body.id}/context`, {
    fields: {
      purpose: "Checkpoint 2: a web app whose sessions end when idle.",
      scope_in: "Session handling.",
      scope_out: "Payments.",
      actors: ["Customer", "Support agent"],
      environment: "Web browsers.",
    },
  });
  expect(activated.body.activated).toBe(true);
  return { workspaceId, projectId: created.body.id };
}

interface Requirement {
  requirement_id: string;
  source_req_id: string;
  current_version: number;
}

async function postRequirement(request: APIRequestContext, auth: string, projectId: string, statement: string) {
  const posted = await call<{ requirement: Requirement }>(request, auth, "POST", `/projects/${projectId}/requirements`, {
    fields: { template: "free_text", slots: { statement }, type: "functional", priority: "must", tags: [], acceptance_criteria: [] },
  });
  expect(posted.status).toBe(201);
  return posted.body.requirement;
}

/** Proposed → Under review → Approved, once analysis has finished on the current text. */
async function approveRequirement(request: APIRequestContext, auth: string, requirement: Requirement) {
  const path = `/requirements/${requirement.requirement_id}`;
  const version = requirement.current_version;
  expect((await call(request, auth, "PATCH", path, { state: "Under_Review", version })).status).toBe(200);
  await expect
    .poll(async () => (await call(request, auth, "PATCH", path, { state: "Approved", version })).status, {
      timeout: AI_MS,
      message: `${requirement.source_req_id} approved once its analysis is current`,
    })
    .toBe(200);
}

/** The access token lives in memory only (US-19), so every full page load signs in again. */
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

async function freeze(page: Page, label: string) {
  const form = page.getByRole("form", { name: "Freeze a baseline" });
  await form.getByLabel("Label").fill(label);
  await form.getByRole("button", { name: "Freeze baseline" }).click();
  await expect(page.getByRole("row", { name: new RegExp(`^${label.replace(".", "\\.")}`) })).toBeVisible();
}

test("CP2: rule conflict → issue for both owners → AI suggestions → edited and accepted → decided → merged → v1.1 vs v1.0", async ({
  browser,
  request,
}) => {
  const [owner, analyst, developer, manager] = await Promise.all(
    [OWNER, ANALYST, DEVELOPER, MANAGER].map((email) => token(request, email)),
  );
  const { workspaceId, projectId } = await cp2Project(request, owner);
  const base = `/w/${workspaceId}/p/${projectId}`;
  const a = await postRequirement(request, analyst, projectId, A_TEXT);
  const b = await postRequirement(request, developer, projectId, B_TEXT);

  // 1. Both approved and frozen as v1.0 (US-40). The rule finding is Medium, so it does not block.
  await approveRequirement(request, manager, a);
  await approveRequirement(request, manager, b);
  const managerPage = await open(browser, MANAGER, `${base}/baselines`);
  await freeze(managerPage, "v1.0");

  // 2. The rule check (US-58) found what the similarity filter skips; the auto issue is assigned to
  //    both owners, and reaches the developer's inbox (US-38).
  interface Issue { id: string; number: number; status: string; finding_id: string; labels: string[]; assignees: { full_name: string }[] }
  let issue: Issue | undefined;
  await expect
    .poll(async () => {
      const page = await call<{ items: Issue[] }>(request, analyst, "GET", `/projects/${projectId}/issues?auto=true`);
      issue = page.body.items[0];
      return Boolean(issue);
    }, { timeout: CHECKS_MS, message: "an auto conflict issue" })
    .toBe(true);
  expect(issue!.labels).toContain("conflict");
  expect(issue!.assignees.map((p) => p.full_name).sort()).toEqual(["Demo Business Analyst", "Demo Developer"]);
  const finding = await call<{ source: string; rule_id: string }>(request, analyst, "GET", `/findings/${issue!.finding_id}`);
  expect(finding.body).toMatchObject({ source: "Rule", rule_id: "numeric_limit" });
  const issuePath = `${base}/issues/${issue!.id}`;

  const developerPage = await open(browser, DEVELOPER, "/inbox");
  await developerPage.getByRole("link", { name: new RegExp(`ISS-${issue!.number}\\b`) }).first().click();
  await expect(developerPage).toHaveURL(new RegExp(`/issues/${issue!.id}$`));

  // 3. Three AI options (US-45); both owners back option A.
  const developerPanel = developerPage.getByRole("region", { name: "Suggested solutions" });
  await expect(developerPanel.getByRole("radio")).toHaveCount(3, { timeout: AI_MS });
  await developerPanel.getByRole("button", { name: "Mark A as my preference" }).click();
  const analystPage = await open(browser, ANALYST, issuePath);
  const analystPanel = analystPage.getByRole("region", { name: "Suggested solutions" });
  await analystPanel.getByRole("button", { name: "Mark A as my preference" }).click();
  await visit(analystPage, ANALYST, issuePath);
  await expect(analystPanel.locator(".preference-marks").first()).toContainText("Demo Developer ✓");
  await expect(analystPanel.locator(".preference-marks").first()).toContainText("Demo Business Analyst ✓");

  // 4. The manager edits option A and accepts it: the change editor opens pre-filled, linked to the
  //    suggestion and the issue; the requirement itself is untouched until a merge.
  const suggestion = await call<{ id: string; options: { target_requirement_id: string }[] }>(
    request, manager, "GET", `/findings/${issue!.finding_id}/suggestions`,
  ); // prettier-ignore
  const target = suggestion.body.options[0].target_requirement_id === a.requirement_id ? a : b;
  const agreed = target === a
    ? "The session shall expire after 5 minutes of inactivity."
    : "The session shall time out after 30 minutes.";  // prettier-ignore
  await visit(managerPage, MANAGER, issuePath);
  const managerPanel = managerPage.getByRole("region", { name: "Suggested solutions" });
  await managerPanel.getByRole("button", { name: "Edit A first" }).click();
  await managerPanel.getByLabel("Your wording").fill(agreed);
  await managerPanel.getByRole("button", { name: "Accept edited text → open change" }).click();
  await expect(managerPage).toHaveURL(/\/changes\/new\?requirement=/);
  await expect(managerPage.getByText(/Suggested by AI, accepted by you/)).toBeVisible();
  await expect(managerPage.getByLabel("Proposed text")).toHaveValue(agreed);
  await managerPage.getByRole("button", { name: "Open change request" }).click();
  await expect(managerPage).toHaveURL(/\/changes\/[0-9a-f-]+$/);
  const changeId = managerPage.url().split("/").pop()!;
  const change = await call<{ source_suggestion_id: string; resolves: { key: string }[] }>(
    request, manager, "GET", `/change-requests/${changeId}`,
  ); // prettier-ignore
  expect(change.body.source_suggestion_id).toBe(suggestion.body.id);
  expect(change.body.resolves.map((r) => r.key)).toContain(`ISS-${issue!.number}`);

  // 5. The decision owner (US-57: the default rule, the target's owner) approves once the checks are
  //    in; the analyst merges, and the issue closes with its finding.
  const crPath = `${base}/changes/${changeId}`;
  const decision = await call<{ owners: { full_name: string }[]; sentence: string }>(
    request, manager, "GET", `/change-requests/${changeId}/decision`,
  ); // prettier-ignore
  const decider = EMAIL_OF[decision.body.owners[0].full_name];
  expect(decider).toBe(target === a ? ANALYST : DEVELOPER);
  const deciderPage = decider === ANALYST ? analystPage : developerPage;
  await visit(deciderPage, decider, crPath);
  await expect(deciderPage.getByText(decision.body.sentence)).toBeVisible();
  await deciderPage.getByRole("tab", { name: /^Checks/ }).click();
  await expect(deciderPage.getByRole("region", { name: "Findings delta" })).toBeVisible({ timeout: CHECKS_MS });
  await deciderPage.getByRole("tab", { name: /^Conversation/ }).click();
  const review = deciderPage.getByRole("form", { name: "Your review" });
  await review.getByRole("radio", { name: "Approve" }).check();
  await review.getByRole("button", { name: "Send review" }).click();
  await expect(deciderPage.getByText(/Review sent on revision/)).toBeVisible();

  await visit(analystPage, ANALYST, crPath);
  const merge = analystPage.getByRole("button", { name: "Merge into baseline" });
  await expect(merge).toBeEnabled();
  await merge.click();
  await expect(analystPage.getByText(`Merged: ${target.source_req_id} is now v2.`)).toBeVisible();
  await expect
    .poll(async () => (await call<Issue>(request, analyst, "GET", `/issues/${issue!.id}`)).body.status, {
      timeout: CHECKS_MS,
      message: "the auto issue closes with its finding",
    })
    .toBe("closed");

  // 6. Snapshot v1.1 compared with v1.0: one changed, with the agreed text.
  await visit(managerPage, MANAGER, `${base}/baselines`);
  await freeze(managerPage, "v1.1");
  await managerPage.getByRole("row", { name: /^v1\.0/ }).getByRole("radio", { name: "from" }).check();
  await managerPage.getByRole("row", { name: /^v1\.1/ }).getByRole("radio", { name: "to" }).check();
  const comparison = managerPage.getByRole("region", { name: "v1.0 compared with v1.1" });
  await expect(comparison).toContainText("0 added · 1 changed · 0 removed · 1 unchanged");
  await expect(comparison).toContainText(`~ ${target.source_req_id} v1 → v2`);
  await expect(comparison.getByLabel(`Changes to ${target.source_req_id}`).locator("ins")).toContainText(
    target === a ? "5" : "30",
  );
});
