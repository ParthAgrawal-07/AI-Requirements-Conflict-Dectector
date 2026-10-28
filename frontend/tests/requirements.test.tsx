import { afterEach, describe, expect, it, vi } from "vitest";
import { RequirementsPage } from "../src/features/requirements/RequirementsPage";
import { RequirementsTable } from "../src/features/requirements/RequirementsTable";
import { Tabs } from "../src/components/Tabs";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

const REQ = {
  requirement_id: "r1",
  project_id: "p1",
  document_id: "d1",
  source_req_id: "REQ-014",
  body: "When the user is inactive for 30 minutes, the system shall end the session.",
  location: "paragraph 3",
  order_index: 0,
  stakeholder_group: "Security",
  is_protected: true,
  current_version: 2,
  state: "Approved",
  origin: "document",
  owner_id: "u1",
  owner_name: "Riya",
  section_heading: null,
  needs_review: false,
  review_reasons: [],
};

const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const perms = (permissions: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Viewer", is_default: true },
  permissions,
  protected_only: [],
});

afterEach(() => vi.unstubAllGlobals());

describe("RequirementsTable", () => {
  it("shows printed ID, text, state with version, owner, origin and group", async () => {
    mockApi({ "GET /api/v1/projects/p1/requirements": page([REQ]) });
    renderWithProviders(<RequirementsTable projectId="p1" />);

    const row = (await screen.findByText("REQ-014", { exact: false })).closest("tr")!;
    expect(within(row).getByText(/inactive for 30 minutes/)).toBeInTheDocument();
    expect(within(row).getByText("Approved v2")).toBeInTheDocument();
    expect(within(row).getByText("Riya")).toBeInTheDocument();
    expect(within(row).getByText("Document")).toBeInTheDocument();
    expect(within(row).getByLabelText("Protected")).toBeInTheDocument();
  });

  it("filters by state on the server", async () => {
    const { calls } = mockApi({ "GET /api/v1/projects/p1/requirements": page([REQ]) });
    const { user } = renderWithProviders(<RequirementsTable projectId="p1" />);
    await screen.findByText("Approved v2");

    await user.click(screen.getByRole("button", { name: "Proposed" }));

    await waitFor(() => expect(calls.some((c) => c.path.includes("state=Proposed"))).toBe(true));
  });

  it("explains an empty list, and a failed extraction", async () => {
    mockApi({ "GET /api/v1/projects/p1/requirements": page([]) });
    const { unmount } = renderWithProviders(<RequirementsTable projectId="p1" />);
    expect(await screen.findByText(/No requirements yet/)).toBeInTheDocument();
    unmount();

    renderWithProviders(<RequirementsTable projectId="p1" extractionFailed />);
    expect(await screen.findByText(/Extraction failed/)).toBeInTheDocument();
  });

  it("flags items extraction was unsure about", async () => {
    mockApi({
      "GET /api/v1/projects/p1/requirements": page([
        { ...REQ, source_req_id: null, needs_review: true, review_reasons: ["No modal verb"] },
      ]),
    });
    renderWithProviders(<RequirementsTable projectId="p1" />);
    expect(await screen.findByText("Check extraction")).toBeInTheDocument();
  });
});

describe("RequirementsPage permissions", () => {
  const routes = (permissions: string[]) => ({
    "GET /api/v1/projects/p1": { id: "p1", name: "Mobile Banking" },
    "GET /api/v1/projects/p1/documents": page([]),
    "GET /api/v1/projects/p1/requirements": page([]),
    "GET /api/v1/me/permissions": perms(permissions),
  });

  it("hides Upload SRS from a viewer", async () => {
    mockApi(routes(["view"]));
    renderWithProviders(<RequirementsPage />, {
      route: "/w/w1/p/p1/requirements",
      path: "/w/:workspaceId/p/:projectId/requirements",
    });
    await screen.findByText("Mobile Banking");
    expect(screen.queryByRole("button", { name: "Upload SRS" })).not.toBeInTheDocument();
  });

  it("shows it to a member with doc.upload, and live progress of a running upload", async () => {
    mockApi({
      ...routes(["view", "doc.upload"]),
      "GET /api/v1/projects/p1/documents": page([
        {
          document_id: "d1",
          project_id: "p1",
          filename: "srs.docx",
          format: "docx",
          size_bytes: 1,
          status: "processing",
          progress_percent: 60,
          error_message: null,
          requirement_count: 0,
          import_mode: "proposals",
          stakeholder_group: null,
          uploaded_by: "u1",
          uploaded_at: "2026-10-24T00:00:00Z",
        },
      ]),
    });
    renderWithProviders(<RequirementsPage />, {
      route: "/w/w1/p/p1/requirements",
      path: "/w/:workspaceId/p/:projectId/requirements",
    });
    expect(await screen.findByRole("button", { name: "Upload SRS" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /srs.docx/ })).toHaveAttribute(
      "aria-valuenow",
      "60",
    );
  });
});

describe("Tabs", () => {
  it("moves between tabs with the arrow keys", async () => {
    const onSelect = vi.fn();
    const { user } = renderWithProviders(
      <Tabs
        label="t"
        selected="a"
        onSelect={onSelect}
        tabs={[
          { id: "a", label: "A" },
          { id: "b", label: "B" },
        ]}
      >
        panel
      </Tabs>,
    );
    screen.getByRole("tab", { name: "A" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(onSelect).toHaveBeenCalledWith("b");
  });
});
