import { describe, expect, it } from "vitest";
import { fireEvent, mockApi, renderWithProviders, screen } from "./test-utils";
import { DocumentProgressList, UploadDialog } from "../src/features/projects/UploadDialog";
import type { DocumentRead } from "../src/api/types";

const perms = (permissions: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Developer", is_default: false },
  permissions,
  protected_only: [],
});

describe("UploadDialog", () => {
  it("renders upload form and shows baseline option only with baseline.manage permission", async () => {
    mockApi({
      "GET /api/v1/me/permissions?project=p1": perms(["doc.upload", "baseline.manage"]),
    });

    renderWithProviders(<UploadDialog projectId="p1" open={true} onClose={() => {}} />);

    expect(await screen.findByRole("dialog", { name: "Upload SRS" })).toBeInTheDocument();
    expect(screen.getByLabelText("Document")).toBeInTheDocument();
    expect(screen.getByLabelText("Stakeholder group (optional)")).toBeInTheDocument();
    expect(await screen.findByLabelText(/Baseline — requirements are already agreed/)).toBeInTheDocument();
  });

  it("hides baseline option when user lacks baseline.manage", async () => {
    mockApi({
      "GET /api/v1/me/permissions?project=p1": perms(["doc.upload"]),
    });

    renderWithProviders(<UploadDialog projectId="p1" open={true} onClose={() => {}} />);

    expect(await screen.findByRole("dialog", { name: "Upload SRS" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Baseline — requirements are already agreed/)).not.toBeInTheDocument();
  });

  it("validates that a file must be selected before submit", async () => {
    mockApi({
      "GET /api/v1/me/permissions?project=p1": perms(["doc.upload"]),
    });

    renderWithProviders(
      <UploadDialog projectId="p1" open={true} onClose={() => {}} />,
    );

    const dialog = await screen.findByRole("dialog", { name: "Upload SRS" });
    const form = dialog.querySelector("form")!;
    fireEvent.submit(form);

    expect(await screen.findByText("Choose a PDF or Word file first.")).toBeInTheDocument();
  });
});

describe("DocumentProgressList", () => {
  it("renders status, progress bar for processing, and error for failed docs", () => {
    const docs: DocumentRead[] = [
      {
        document_id: "doc-1",
        project_id: "p1",
        filename: "specs.pdf",
        format: "pdf",
        size_bytes: 1024,
        import_mode: "proposals",
        stakeholder_group: null,
        status: "processing",
        progress_percent: 60,
        error_message: null,
        requirement_count: 0,
        uploaded_by: "user-1",
        uploaded_at: "2026-10-24T00:00:00Z",
      },
      {
        document_id: "doc-2",
        project_id: "p1",
        filename: "invalid.docx",
        format: "docx",
        size_bytes: 2048,
        import_mode: "proposals",
        stakeholder_group: null,
        status: "failed",
        progress_percent: 10,
        error_message: "Corrupt document archive",
        requirement_count: 0,
        uploaded_by: "user-1",
        uploaded_at: "2026-10-24T00:00:00Z",
      },
    ];

    renderWithProviders(<DocumentProgressList documents={docs} />);

    expect(screen.getByText("specs.pdf")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");

    expect(screen.getByText("invalid.docx")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Corrupt document archive")).toBeInTheDocument();
  });
});
