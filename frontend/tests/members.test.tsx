import { afterEach, describe, expect, it, vi } from "vitest";
import { JoinCodesTab, joinLink } from "../src/features/members/JoinCodesTab";
import { JoinPage } from "../src/features/members/JoinPage";
import { makeGraph } from "../src/features/prototypes/MapSpike";
import { changedValues, toForm } from "../src/features/setup/SetupWizard";
import { SetupBanner } from "../src/features/setup/SetupBanner";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

const role = (id: string, name: string, grantable = true) => ({
  id,
  name,
  is_default: true,
  description: null,
  permissions: ["view"],
  grantable_by_join_code: grantable,
});
const ROLES = [role("r-own", "Owner", false), role("r-adm", "Admin", false), role("r-dev", "Developer"), role("r-stk", "Stakeholder")];
const CODE = {
  id: "c1",
  workspace_id: "w1",
  project_id: null,
  code_hint: "4XPA",
  role: { id: "r-dev", name: "Developer", is_default: true },
  expires_at: "2026-10-30T00:00:00Z",
  max_uses: 20,
  uses: 3,
  requires_approval: false,
  status: "active",
  created_by: "u1",
  created_at: "2026-10-23T00:00:00Z",
  revoked_at: null,
};
const REQUEST = {
  id: "jr1",
  workspace_id: "w1",
  project_id: null,
  join_code_id: "c1",
  user: { id: "u9", full_name: "Neha Iyer", email: "neha@acme.in" },
  role: { id: "r-dev", name: "Developer", is_default: true },
  status: "pending",
  created_at: new Date().toISOString(),
  decided_by: null,
  decided_at: null,
};

const baseRoutes = {
  "GET /api/v1/workspaces/w1/roles": ROLES,
  "GET /api/v1/workspaces/w1/projects": { items: [], total: 0, limit: 100, offset: 0 },
  "GET /api/v1/workspaces/w1/join-codes": [CODE],
  "GET /api/v1/workspaces/w1/join-requests": [REQUEST],
};

afterEach(() => vi.unstubAllGlobals());

describe("JoinCodesTab", () => {
  it("never offers Owner or Admin", async () => {
    mockApi(baseRoutes);
    renderWithProviders(<JoinCodesTab workspaceId="w1" />);
    const select = await screen.findByLabelText("Role");
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(2));
    expect(within(select).queryByText("Owner")).not.toBeInTheDocument();
    expect(within(select).queryByText("Admin")).not.toBeInTheDocument();
  });

  it("creates a code and shows it once, with the chosen expiry and approval", async () => {
    const { calls } = mockApi({
      ...baseRoutes,
      "POST /api/v1/workspaces/w1/join-codes": [201, { ...CODE, id: "c2", code: "K7QM-4XPA" }],
    });
    const { user } = renderWithProviders(<JoinCodesTab workspaceId="w1" />);
    await screen.findByText("…4XPA");

    await user.click(screen.getByLabelText(/30 days/));
    await user.click(screen.getByLabelText(/Approve each person/));
    await user.click(screen.getByRole("button", { name: "Create code" }));

    expect(await screen.findByText("K7QM-4XPA")).toBeInTheDocument();
    expect(screen.getByText(/shown only now/i)).toBeInTheDocument();
    const body = JSON.parse(String(calls.find((c) => c.method === "POST")!.body));
    expect(body).toEqual({
      role_id: "r-dev",
      project_id: null,
      expires_in_days: 30,
      max_uses: 20,
      requires_approval: true,
    });
  });

  it("lists codes by hint with uses, and revokes", async () => {
    const { calls } = mockApi({ ...baseRoutes, "DELETE /api/v1/join-codes/c1": [204, null] });
    const { user } = renderWithProviders(<JoinCodesTab workspaceId="w1" />);
    const row = (await screen.findByText("…4XPA")).closest("tr")!;
    expect(within(row).getByText("3 / 20")).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: /Revoke code ending 4XPA/ }));

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("approves a join request with the role the manager picks", async () => {
    const { calls } = mockApi({
      ...baseRoutes,
      "POST /api/v1/workspaces/w1/join-requests/jr1/decision": { ...REQUEST, status: "approved" },
    });
    const { user } = renderWithProviders(<JoinCodesTab workspaceId="w1" />);
    await screen.findByText("Neha Iyer");

    await user.selectOptions(screen.getByLabelText("Role for Neha Iyer"), "r-stk");
    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() =>
      expect(JSON.parse(String(calls.find((c) => c.method === "POST")!.body))).toEqual({
        approve: true,
        role_id: "r-stk",
      }),
    );
  });

  it("builds the join link from the code", () => {
    expect(joinLink("K7QM-4XPA", "https://rcd.app")).toBe("https://rcd.app/join/K7QM-4XPA");
  });
});

describe("JoinPage", () => {
  it("sends a signed-out visitor with a link to sign-up with the code filled in", () => {
    renderWithProviders(<JoinPage />, { route: "/join/K7QM-4XPA", path: "/join/:code" });
    expect(screen.getByText("navigated away")).toBeInTheDocument();
  });
});

describe("Setup wizard", () => {
  it("round-trips the brief and sends only changed fields", () => {
    const saved = toForm({
      purpose: "Banking",
      actors: ["Customer", "Teller"],
      glossary: [{ term: "OTP", meaning: "one-time password" }],
    });
    expect(saved.actors).toBe("Customer\nTeller");
    expect(saved.glossary).toBe("OTP: one-time password");

    const edited = { ...saved, actors: "Customer\nTeller\n Auditor ", scope_in: "Payments" };
    expect(changedValues(edited, saved)).toEqual({
      actors: ["Customer", "Teller", "Auditor"],
      scope_in: "Payments",
    });
    expect(changedValues(saved, saved)).toEqual({});
  });

  it("shows the Setup banner with the missing fields", async () => {
    mockApi({
      "GET /api/v1/projects/p1": { id: "p1", name: "Mobile Banking", status: "setup" },
      "GET /api/v1/projects/p1/context": {
        project_id: "p1",
        project_status: "setup",
        context_version: 0,
        latest: null,
        fields: [],
        missing_fields: ["Scope (in and out)", "User classes and actors"],
        required_confirmed: 2,
        required_total: 4,
      },
    });
    renderWithProviders(<SetupBanner workspaceId="w1" projectId="p1" />);
    expect(
      await screen.findByText(/Missing: Scope \(in and out\), User classes and actors/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open setup" })).toHaveAttribute(
      "href",
      "/w/w1/p/p1/setup",
    );
  });
});

describe("map spike", () => {
  it("builds the same graph every time", () => {
    const first = makeGraph(500, 2000);
    expect(first.nodes).toHaveLength(500);
    expect(first.edges).toHaveLength(2000);
    expect(makeGraph(500, 2000)).toEqual(first);
  });
});
