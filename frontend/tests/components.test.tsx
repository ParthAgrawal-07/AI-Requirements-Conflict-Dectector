import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "./test-utils";
import {
  Button,
  Input,
  Textarea,
  Select,
  FilterDropdown,
  SeverityBadge,
  StatusBadge,
  CategoryBadge,
  ConfidenceBadge,
  RequirementBadge,
  StatCard,
  RequirementCard,
  AIExplanationCard,
  DataTable,
  Column,
  Modal,
  ConfirmDialog,
  ToastProvider,
  useToast,
  Spinner,
  ProgressBar,
  TopNav,
  Sidebar,
} from "../src/components/ui";

describe("Button component", () => {
  it("renders with default props and handles click", async () => {
    const handleClick = vi.fn();
    const { user } = renderWithProviders(
      <Button onClick={handleClick}>Submit</Button>
    );

    const btn = screen.getByRole("button", { name: /submit/i });
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(handleClick).toHaveBeenCalledOnce();
  });

  it("handles loading state and disables interaction", async () => {
    const handleClick = vi.fn();
    const { user } = renderWithProviders(
      <Button isLoading onClick={handleClick}>
        Saving
      </Button>
    );

    const btn = screen.getByRole("button", { name: /saving/i });
    expect(btn).toBeDisabled();
    await user.click(btn);
    expect(handleClick).not.toHaveBeenCalled();
  });

  it("renders distinct variants", () => {
    const { rerender } = renderWithProviders(
      <Button variant="danger">Delete</Button>
    );
    expect(screen.getByRole("button", { name: /delete/i })).toHaveClass("bg-red-600");

    rerender(<Button variant="outline">Cancel</Button>);
    expect(screen.getByRole("button", { name: /cancel/i })).toHaveClass("border-slate-300");
  });
});

describe("Input & Textarea components", () => {
  it("renders input with label and helper text", () => {
    renderWithProviders(
      <Input label="Email address" helperText="Enter work email" />
    );

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByText(/enter work email/i)).toBeInTheDocument();
  });

  it("renders error state when error is passed", () => {
    renderWithProviders(
      <Input label="Finding ID" error="Finding ID already exists" />
    );

    expect(screen.getByText(/finding id already exists/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/finding id/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("triggers onClear when clear button is clicked", async () => {
    const handleClear = vi.fn();
    const { user } = renderWithProviders(
      <Input
        label="Search"
        value="Session timeout"
        onChange={() => {}}
        onClear={handleClear}
      />
    );

    const clearBtn = screen.getByRole("button", { name: /clear input/i });
    await user.click(clearBtn);
    expect(handleClear).toHaveBeenCalledOnce();
  });

  it("renders textarea with char count and draft badge", () => {
    renderWithProviders(
      <Textarea
        label="Reviewer Notes"
        badge={<span>Draft</span>}
        value="Initial assessment"
        maxLength={100}
        showCharCount
        readOnly
      />
    );

    expect(screen.getByLabelText(/reviewer notes/i)).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("18/100")).toBeInTheDocument();
  });
});

describe("Select & FilterDropdown components", () => {
  it("renders Select options correctly", () => {
    renderWithProviders(
      <Select
        label="Environment"
        options={[
          { value: "prod", label: "Production" },
          { value: "dev", label: "Development" },
        ]}
      />
    );

    expect(screen.getByLabelText(/environment/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("toggles and selects FilterDropdown options", async () => {
    const handleChange = vi.fn();
    const { user } = renderWithProviders(
      <FilterDropdown
        label="Severity"
        value="all"
        options={[
          { value: "all", label: "All" },
          { value: "high", label: "High" },
          { value: "low", label: "Low" },
        ]}
        onChange={handleChange}
      />
    );

    const triggerBtn = screen.getByRole("button", { name: /severity:/i });
    expect(triggerBtn).toHaveTextContent("All");

    await user.click(triggerBtn);
    const highOption = screen.getByRole("option", { name: "High" });
    await user.click(highOption);

    expect(handleChange).toHaveBeenCalledWith("high");
  });
});

describe("Badge components", () => {
  it("renders SeverityBadge correctly", () => {
    const { rerender } = renderWithProviders(<SeverityBadge severity="High" />);
    expect(screen.getByText("High")).toHaveClass("text-red-700");

    rerender(<SeverityBadge severity="medium" />);
    expect(screen.getByText("Medium")).toHaveClass("text-amber-700");

    rerender(<SeverityBadge severity="low" />);
    expect(screen.getByText("Low")).toHaveClass("text-blue-700");
  });

  it("renders StatusBadge with correct labels and colors", () => {
    const { rerender } = renderWithProviders(
      <StatusBadge status="Pending Review" />
    );
    expect(screen.getByText("Pending Review")).toHaveClass("text-blue-700");

    rerender(<StatusBadge status="Awaiting Clarification" />);
    expect(screen.getByText("Awaiting Clarification")).toHaveClass("text-amber-700");

    rerender(<StatusBadge status="Resolved" />);
    expect(screen.getByText("Resolved")).toHaveClass("text-emerald-700");

    rerender(<StatusBadge status="Dismissed" />);
    expect(screen.getByText("Dismissed")).toBeInTheDocument();
  });

  it("renders CategoryBadge and RequirementBadge", () => {
    renderWithProviders(
      <div>
        <CategoryBadge category="Conflicting" />
        <RequirementBadge reqId="R12" />
      </div>
    );

    expect(screen.getByText("Conflicting")).toBeInTheDocument();
    expect(screen.getByText("R12")).toBeInTheDocument();
  });

  it("renders ConfidenceBadge in pill and compact modes", () => {
    const { rerender } = renderWithProviders(
      <ConfidenceBadge confidence={0.92} />
    );
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByText("AI confidence")).toBeInTheDocument();

    rerender(<ConfidenceBadge confidence={0.88} variant="compact" />);
    expect(screen.getByText("88%")).toBeInTheDocument();
    expect(screen.queryByText("AI confidence")).not.toBeInTheDocument();
  });
});

describe("Card and StatCard components", () => {
  it("renders StatCard with value and label", () => {
    renderWithProviders(
      <StatCard
        value="6"
        label="Total findings"
        description="Across 12 requirements"
      />
    );

    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("Total findings")).toBeInTheDocument();
    expect(screen.getByText("Across 12 requirements")).toBeInTheDocument();
  });

  it("renders RequirementCard matching Conflict Review design", () => {
    renderWithProviders(
      <RequirementCard
        id="R12"
        title="Inactivity logout"
        body="The system shall log users out after 5 minutes of inactivity."
        version="v1.4"
        category="Security requirements"
        section="§3.2"
        owner="Priya Shah"
      />
    );

    expect(screen.getByText("R12")).toBeInTheDocument();
    expect(screen.getByText("Inactivity logout")).toBeInTheDocument();
    expect(screen.getByText(/5 minutes of inactivity/i)).toBeInTheDocument();
    expect(screen.getByText(/Priya Shah/i)).toBeInTheDocument();
  });

  it("renders AIExplanationCard with confidence score", () => {
    renderWithProviders(
      <AIExplanationCard
        severity="High"
        confidence={0.92}
        explanation="Possible timing contradiction."
        recommendation="Clarify session definition."
      />
    );

    expect(screen.getByText("AI explanation")).toBeInTheDocument();
    expect(screen.getByText(/Possible timing contradiction/i)).toBeInTheDocument();
    expect(screen.getByText(/Clarify session definition/i)).toBeInTheDocument();
  });
});

describe("DataTable component", () => {
  interface RowItem {
    id: string;
    title: string;
    count: number;
  }

  const columns: Column<RowItem>[] = [
    { key: "id", header: "ID", sortable: true },
    { key: "title", header: "Title", sortable: true },
    { key: "count", header: "Count", sortable: true },
  ];

  const data: RowItem[] = [
    { id: "1", title: "Alpha", count: 10 },
    { id: "2", title: "Beta", count: 20 },
    { id: "3", title: "Gamma", count: 5 },
  ];

  it("renders table data rows and columns", () => {
    renderWithProviders(<DataTable data={data} columns={columns} />);

    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Gamma")).toBeInTheDocument();
    expect(screen.getByText(/Showing 1–3 of 3/i)).toBeInTheDocument();
  });

  it("sorts data when sortable header is clicked", async () => {
    const { user } = renderWithProviders(
      <DataTable data={data} columns={columns} />
    );

    const titleHeader = screen.getByRole("button", { name: /title/i });
    await user.click(titleHeader);

    const cells = screen.getAllByRole("cell");
    expect(cells[1]).toHaveTextContent("Alpha");
  });

  it("renders empty message when data is empty", () => {
    renderWithProviders(
      <DataTable data={[]} columns={columns} emptyMessage="No items to show." />
    );

    expect(screen.getByText("No items to show.")).toBeInTheDocument();
  });
});

describe("Modal and ConfirmDialog components", () => {
  it("renders Modal when isOpen is true and calls onClose", async () => {
    const handleClose = vi.fn();
    const { user } = renderWithProviders(
      <Modal isOpen={true} onClose={handleClose} title="Test Modal">
        <p>Modal body content</p>
      </Modal>
    );

    expect(screen.getByText("Test Modal")).toBeInTheDocument();
    expect(screen.getByText("Modal body content")).toBeInTheDocument();

    const closeBtn = screen.getByRole("button", { name: /close/i });
    await user.click(closeBtn);
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it("renders ConfirmDialog and fires onConfirm callback", async () => {
    const handleConfirm = vi.fn();
    const handleClose = vi.fn();
    const { user } = renderWithProviders(
      <ConfirmDialog
        isOpen={true}
        onClose={handleClose}
        onConfirm={handleConfirm}
        title="Delete Item"
        description="Are you sure?"
        confirmLabel="Yes, delete"
      />
    );

    expect(screen.getByText("Delete Item")).toBeInTheDocument();
    const confirmBtn = screen.getByRole("button", { name: "Yes, delete" });
    await user.click(confirmBtn);
    expect(handleConfirm).toHaveBeenCalledOnce();
  });
});

describe("Toast notification system", () => {
  function TestToastConsumer() {
    const toast = useToast();
    return (
      <button
        type="button"
        onClick={() => toast.success("Conflict resolved successfully.")}
      >
        Trigger Toast
      </button>
    );
  }

  it("triggers and displays toast notification", async () => {
    const { user } = renderWithProviders(
      <ToastProvider>
        <TestToastConsumer />
      </ToastProvider>
    );

    const btn = screen.getByRole("button", { name: /trigger toast/i });
    await user.click(btn);

    expect(
      screen.getByText("Conflict resolved successfully.")
    ).toBeInTheDocument();
  });
});

describe("Loading and navigation indicators", () => {
  it("renders Spinner and ProgressBar", () => {
    renderWithProviders(
      <div>
        <Spinner size="lg" />
        <ProgressBar value={75} label="Extraction" showValue />
      </div>
    );

    expect(screen.getByLabelText(/loading/i)).toBeInTheDocument();
    expect(screen.getByText("Extraction")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
  });

  it("renders TopNav with user initials and role", () => {
    renderWithProviders(
      <TopNav
        appName="Requirements Conflict Detector"
        userName="Abhijeet"
        userRole="Reviewer"
        userInitials="AB"
      />
    );

    expect(screen.getByText("Requirements Conflict Detector")).toBeInTheDocument();
    expect(screen.getByText("Abhijeet")).toBeInTheDocument();
    expect(screen.getByText("Reviewer")).toBeInTheDocument();
    expect(screen.getByText("AB")).toBeInTheDocument();
  });

  it("renders Sidebar and handles navigation clicks", async () => {
    const handleNavigate = vi.fn();
    const { user } = renderWithProviders(
      <Sidebar currentPath="/findings" onNavigate={handleNavigate} />
    );

    const reqLink = screen.getByRole("button", { name: /requirements/i });
    await user.click(reqLink);
    expect(handleNavigate).toHaveBeenCalledWith("/requirements");
  });
});
