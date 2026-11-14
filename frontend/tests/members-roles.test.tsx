import { afterEach, describe, expect, it, vi } from "vitest";
import { MembersTab } from "../src/features/members/MembersTab";
import { describeRole } from "../src/features/members/RoleEditor";
import { RolesTab } from "../src/features/members/RolesTab";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

vi.mock("../src/app/auth", async (original) => ({
  ...(await original<typeof import("../src/app/auth")>()),
  useAuth: () => ({ user: { id: "u-me", full_name: "Me" }, token: "t", loading: false }),
}));

const role = (id: string, name: string, permissions: string[], is_default = true) => ({
  id,
  name,
  is_default,
  description: null,
  permissions,
  grantable_by_join_code: !permissions.includes("roles.manage"),
});
const OWNER_PERMS = ["view", "message.post", "req.propose", "req.comment", "rcr.review", "rcr.merge", "members.manage", "roles.manage", "workspace.manage"];
const ROLES = [
  role("r-own", "Owner", OWNER_PERMS),
  role("r-dev", "Developer", ["view", "message.post", "req.propose", "rcr.review"]),
  role("r-cr", "Client reviewer", ["view", "req.comment", "rcr.review"], false),
];
const member = (id: string, name: string, roleId: string, roleName: string) => ({
  user: { id, full_name: name, email: `${id}@acme.in` },
  role: { id: roleId, name: roleName, is_default: true },
  stakeholder_group: null,
  joined_at: "2026-10-01T00:00:00Z",
});
const CATALOGUE = [
  { name: "view", description: "See dashboards", group: "Workspace" },
  { name: "req.propose", description: "Propose requirements", group: "Requirements" },
  { name: "req.comment", description: "Comment on requirements", group: "Requirements" },
  { name: "rcr.review", description: "Review change requests", group: "Review" },
  { name: "protected.signoff", description: "Sign off protected requirements", group: "Governance" },
];
const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: null,
  role: { id: "r-own", name: "Owner", is_default: true },
  permissions: granted,
  protected_only: [],
});

afterEach(() => vi.unstubAllGlobals());

describe("describeRole", () => {
  it("says in one sentence what a role can and cannot do", () => {
    expect(describeRole(["view", "req.comment", "rcr.review"])).toBe(
      "This role can comment and review change requests, but not propose requirements, post in channels or merge.",
    );
    expect(describeRole(["view"])).toMatch(/^This role can only read, but not/);
  });
});

describe("MembersTab", () => {
  it("lets a manager change a role inline, remove others, and leave as themself", async () => {
    vi.stubGlobal("confirm", () => true);
    const { calls } = mockApi({
      "GET /api/v1/workspaces/w1/members": [member("u-me", "Me", "r-own", "Owner"), member("u-riya", "Riya", "r-dev", "Developer")],
      "GET /api/v1/workspaces/w1/roles": ROLES,
      "GET /api/v1/me/permissions": permissions(OWNER_PERMS),
      "GET /api/v1/workspaces/w1/needs-reassignment": [
        { kind: "requirement", id: "q1", project_id: "p1", label: "REQ-007", former_owner_id: "u-gone", former_owner_name: "Sam" },
      ],
      "PATCH /api/v1/workspaces/w1/members/u-riya": member("u-riya", "Riya", "r-cr", "Client reviewer"),
      "DELETE /api/v1/workspaces/w1/members/u-riya": [204, null],
    });
    const { user } = renderWithProviders(<MembersTab workspaceId="w1" />);

    const select = await screen.findByLabelText("Role of Riya");
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(3));
    await user.selectOptions(select, "r-cr");
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.method === "PATCH")?.body))).toEqual({ role_id: "r-cr" });

    const riya = screen.getByText("Riya").closest("tr") as HTMLElement;
    await user.click(within(riya).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));

    const me = screen.getByText("(you)").closest("tr") as HTMLElement;
    expect(within(me).queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(within(me).getByRole("button", { name: "Leave workspace" })).toBeInTheDocument();
    expect(await screen.findByText(/REQ-007/)).toBeInTheDocument();
    expect(screen.getByText("(former member)")).toBeInTheDocument();
  });

  it("shows roles as text to members who cannot manage them", async () => {
    mockApi({
      "GET /api/v1/workspaces/w1/members": [member("u-riya", "Riya", "r-dev", "Developer")],
      "GET /api/v1/workspaces/w1/roles": ROLES,
      "GET /api/v1/me/permissions": permissions(["view"]),
    });
    renderWithProviders(<MembersTab workspaceId="w1" />);

    expect(await screen.findByText("Developer")).toBeInTheDocument();
    expect(screen.queryByLabelText("Role of Riya")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  });
});

describe("RolesTab", () => {
  it("creates a custom role from the permission checklist", async () => {
    const { calls } = mockApi({
      "GET /api/v1/workspaces/w1/roles": ROLES,
      "GET /api/v1/permissions": CATALOGUE,
      "GET /api/v1/me/permissions": permissions(OWNER_PERMS),
      "POST /api/v1/workspaces/w1/roles": role("r-new", "Client reviewer", ["view", "rcr.review"], false),
    });
    const { user } = renderWithProviders(<RolesTab workspaceId="w1" />);

    await user.click(await screen.findByRole("button", { name: "+ Custom role" }));
    const editor = await screen.findByRole("dialog", { name: "New custom role" });
    await user.type(within(editor).getByLabelText("Name"), "Client reviewer");
    await user.click(await within(editor).findByLabelText(/Review change requests/));
    expect(within(editor).getByText(/This role can review change requests, but not propose/)).toBeInTheDocument();
    // The Owner never holds protected.signoff, so it cannot be ticked (the server refuses it too).
    expect(within(editor).getByLabelText(/Sign off protected requirements/)).toBeDisabled();
    await user.click(within(editor).getByRole("button", { name: "Create role" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.method === "POST")?.body))).toEqual({
      name: "Client reviewer",
      description: null,
      permissions: ["rcr.review", "view"],
    });
  });

  it("keeps default roles read-only and offers Edit and Delete on custom ones", async () => {
    mockApi({
      "GET /api/v1/workspaces/w1/roles": ROLES,
      "GET /api/v1/permissions": CATALOGUE,
      "GET /api/v1/me/permissions": permissions(OWNER_PERMS),
    });
    renderWithProviders(<RolesTab workspaceId="w1" />);

    const custom = (await screen.findByText("Client reviewer")).closest("li") as HTMLElement;
    expect(within(custom).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    const developer = screen.getByText("Developer").closest("li") as HTMLElement;
    expect(within(developer).queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });
});
