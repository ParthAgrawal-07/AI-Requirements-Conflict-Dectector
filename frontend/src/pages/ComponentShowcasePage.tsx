import React, { useState } from "react";
import {
  PageHeader,
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
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  RequirementCard,
  AIExplanationCard,
  Modal,
  ConfirmDialog,
  Drawer,
  Tabs,
  Spinner,
  Skeleton,
  ProgressBar,
  DataTable,
  Column,
  SearchIcon,
  CheckIcon,
  MessageSquareIcon,
  useToast,
} from "../components/ui";

export function ComponentShowcasePage() {
  const toast = useToast();

  // Component interactive states
  const [activeTab, setActiveTab] = useState("buttons");
  const [inputVal, setInputVal] = useState("Sample search text");
  const [textareaVal, setTextareaVal] = useState("Example reviewer notes for draft");
  const [selectVal, setSelectVal] = useState("all");
  const [filterVal, setFilterVal] = useState("high");
  const [buttonLoading, setButtonLoading] = useState(false);
  const [progressVal, setProgressVal] = useState(65);

  // Modals & Drawers
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const tabs = [
    { id: "buttons", label: "Buttons" },
    { id: "inputs", label: "Inputs & Forms" },
    { id: "badges", label: "Badges & Confidence" },
    { id: "cards", label: "Cards & Stats" },
    { id: "tables", label: "Data Tables" },
    { id: "feedback", label: "Feedback & Dialogs" },
  ];

  const triggerLoading = () => {
    setButtonLoading(true);
    setTimeout(() => setButtonLoading(false), 2000);
  };

  interface SampleTableItem {
    id: string;
    name: string;
    category: string;
    priority: string;
  }

  const sampleTableData: SampleTableItem[] = [
    { id: "REQ-01", name: "User Session Timeout", category: "Security", priority: "High" },
    { id: "REQ-02", name: "Report XLSX Export", category: "Reporting", priority: "Medium" },
    { id: "REQ-03", name: "Offline Sync Protocol", category: "Network", priority: "High" },
    { id: "REQ-04", name: "Audit Log Archival", category: "Compliance", priority: "Low" },
  ];

  const sampleColumns: Column<SampleTableItem>[] = [
    { key: "id", header: "Req ID", sortable: true, className: "font-mono font-medium" },
    { key: "name", header: "Requirement Name", sortable: true },
    { key: "category", header: "Category" },
    {
      key: "priority",
      header: "Priority",
      render: (item) => <SeverityBadge severity={item.priority} />,
    },
  ];

  return (
    <div className="space-y-8">
      <PageHeader
        breadcrumbs={[{ label: "Design System" }, { label: "Component Showcase" }]}
        title="UI Component Library"
        description="Comprehensive gallery of reusable UI components built for Sprint 1. Conforms to the visual specification in the Findings List, Conflict Review, and Clarification designs."
      />

      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Tab: Buttons */}
      {activeTab === "buttons" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Button Variants</CardTitle>
              <CardDescription>
                Solid and outline buttons styled for high-contrast accessibility and SaaS aesthetics.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="primary">Primary Action</Button>
                <Button variant="secondary">Secondary Action</Button>
                <Button variant="outline">Outline Action</Button>
                <Button variant="ghost">Ghost Action</Button>
                <Button variant="danger">Danger Action</Button>
              </div>

              <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center gap-3">
                <Button size="sm">Small (sm)</Button>
                <Button size="md">Medium (md)</Button>
                <Button size="lg">Large (lg)</Button>
              </div>

              <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center gap-3">
                <Button
                  variant="primary"
                  leftIcon={<CheckIcon size={16} />}
                >
                  With Left Icon
                </Button>
                <Button
                  variant="outline"
                  rightIcon={<MessageSquareIcon size={16} />}
                >
                  With Right Icon
                </Button>
                <Button
                  variant="primary"
                  isLoading={buttonLoading}
                  onClick={triggerLoading}
                >
                  {buttonLoading ? "Saving..." : "Click for Loading State"}
                </Button>
                <Button disabled variant="primary">
                  Disabled
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tab: Inputs & Forms */}
      {activeTab === "inputs" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Inputs & Textareas</CardTitle>
              <CardDescription>
                Inputs with support for icons, clearable state, error validation, character limits, and draft badges.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-4">
                <Input
                  label="Search with Clear Button"
                  value={inputVal}
                  onChange={(e) => setInputVal(e.target.value)}
                  onClear={() => setInputVal("")}
                  leftIcon={<SearchIcon size={16} />}
                  helperText="Type text then click the (X) icon to clear."
                />

                <Input
                  label="Input with Error Validation"
                  defaultValue="Invalid string format"
                  error="This field contains contradictory syntax."
                />

                <div className="flex gap-4">
                  <Select
                    label="Select Dropdown"
                    value={selectVal}
                    options={[
                      { value: "all", label: "All Items" },
                      { value: "active", label: "Active Only" },
                      { value: "archived", label: "Archived" },
                    ]}
                    onChange={(e) => setSelectVal(e.target.value)}
                  />

                  <div className="space-y-1.5 w-full">
                    <label className="block text-xs font-semibold text-slate-700 tracking-wide">
                      Filter Pill Dropdown
                    </label>
                    <FilterDropdown
                      label="Severity"
                      value={filterVal}
                      options={[
                        { value: "all", label: "All" },
                        { value: "high", label: "High" },
                        { value: "medium", label: "Medium" },
                        { value: "low", label: "Low" },
                      ]}
                      onChange={setFilterVal}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <Textarea
                  label="Reviewer Notes"
                  badge={<span className="text-xs font-mono text-slate-400">Draft · Not submitted</span>}
                  rows={4}
                  value={textareaVal}
                  onChange={(e) => setTextareaVal(e.target.value)}
                  maxLength={200}
                  showCharCount
                  helperText="Draft notes are stored locally until reviewed."
                />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tab: Badges & Confidence */}
      {activeTab === "badges" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Severity Badges</CardTitle>
              <CardDescription>
                High, Medium, Low, Critical severity indicators with distinct colors and shapes.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3">
              <SeverityBadge severity="Critical" />
              <SeverityBadge severity="High" />
              <SeverityBadge severity="Medium" />
              <SeverityBadge severity="Low" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Status Badges</CardTitle>
              <CardDescription>
                State indicators matching the findings workflow (Pending, Awaiting Clarification, Resolved, Dismissed).
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3">
              <StatusBadge status="Pending Review" />
              <StatusBadge status="Awaiting Clarification" />
              <StatusBadge status="Resolved" />
              <StatusBadge status="Dismissed" />
              <StatusBadge status="Accepted" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Category & Requirement Badges</CardTitle>
              <CardDescription>
                Issue categories (Conflicting, Duplicate, Ambiguous, Incomplete, Dependent) and requirement tags.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <CategoryBadge category="Conflicting" />
                <CategoryBadge category="Duplicate" />
                <CategoryBadge category="Ambiguous" />
                <CategoryBadge category="Incomplete" />
                <CategoryBadge category="Dependent" />
              </div>
              <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
                <RequirementBadge reqId="R12" />
                <RequirementBadge reqId="R27" />
                <RequirementBadge reqId="REQ-001" />
                <RequirementBadge reqId="SEC-3.2" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>AI Confidence Badges</CardTitle>
              <CardDescription>
                Confidence percentage displays formatted as pills, bars, or compact scores.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-4">
                <ConfidenceBadge confidence={0.92} />
                <ConfidenceBadge confidence={0.78} />
                <ConfidenceBadge confidence={0.65} />
              </div>
              <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-slate-100">
                <ConfidenceBadge confidence={0.92} showBar />
                <ConfidenceBadge confidence={0.78} showBar />
                <ConfidenceBadge confidence={0.65} showBar />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tab: Cards & Stats */}
      {activeTab === "cards" && (
        <div className="space-y-6">
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-700">KPI Statistic Cards (Findings List)</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                value="6"
                label="Total findings"
                description="Across 12 requirements"
              />
              <StatCard
                value="3"
                label="Pending review"
                description="Ready for assessment"
                valueColor="text-blue-600"
              />
              <StatCard
                value="2"
                label="High severity"
                description="Prioritize these findings"
              />
              <StatCard
                value="1"
                label="Awaiting clarification"
                description="Owner response requested"
              />
            </div>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-700">Requirement Comparison Cards (Conflict Review)</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <RequirementCard
                id="R12"
                title="Inactivity logout"
                version="v1.4"
                body="The system shall log users out after 5 minutes of inactivity."
                category="Security requirements"
                section="§3.2"
                owner="Priya Shah"
              />
              <RequirementCard
                id="R27"
                title="Minimum session duration"
                version="v1.4"
                body="The system shall maintain sessions for at least 30 minutes."
                category="Session requirements"
                section="§4.1"
                owner="Daniel Kim"
              />
            </div>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-700">AI Explanation Card</h3>
            <AIExplanationCard
              title="AI explanation"
              severity="High"
              confidence={0.92}
              explanation='If both requirements describe the same authenticated session, logging out after 5 minutes of inactivity may prevent a session from lasting at least 30 minutes. However, "session" may refer to different layers, or R27 may allow inactivity-based logout.'
              recommendation="Possible conflict, not a confirmed contradiction. Clarify the session definition and any inactivity exception before resolving."
            />
          </div>
        </div>
      )}

      {/* Tab: Data Tables */}
      {activeTab === "tables" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Sortable & Paginated Data Table</CardTitle>
              <CardDescription>
                Interactive data table with sorting indicators, pagination controls, and row clicks.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DataTable
                data={sampleTableData}
                columns={sampleColumns}
                pageSize={3}
                initialSortKey="id"
                footerNote="Click headers to sort ascending / descending."
              />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tab: Feedback & Dialogs */}
      {activeTab === "feedback" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Toast Notifications</CardTitle>
              <CardDescription>
                Trigger toast alerts across all severity types with auto-dismiss.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3">
              <Button
                variant="outline"
                onClick={() => toast.success("Requirement baseline saved successfully.", "Success")}
              >
                Trigger Success Toast
              </Button>
              <Button
                variant="outline"
                onClick={() => toast.error("Failed to parse requirement text in Section 3.2.", "Error")}
              >
                Trigger Error Toast
              </Button>
              <Button
                variant="outline"
                onClick={() => toast.warning("Session timeout setting overrides corporate policy.", "Warning")}
              >
                Trigger Warning Toast
              </Button>
              <Button
                variant="outline"
                onClick={() => toast.info("New clarification response received from Priya Shah.", "Information")}
              >
                Trigger Info Toast
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Modals & Confirmation Dialogs</CardTitle>
              <CardDescription>
                Accessible overlays with keyboard Esc support, backdrop click handling, and focus management.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={() => setIsModalOpen(true)}>
                Open Standard Modal
              </Button>
              <Button variant="outline" onClick={() => setIsConfirmOpen(true)}>
                Open Confirm Dialog
              </Button>
              <Button variant="outline" onClick={() => setIsDrawerOpen(true)}>
                Open Slideover Drawer
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Loading Indicators & Progress</CardTitle>
              <CardDescription>
                Spinners, pulse skeletons, and dynamic progress bars.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center gap-6">
                <Spinner size="sm" />
                <Spinner size="md" />
                <Spinner size="lg" />
                <Spinner size="xl" />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span>Interactive Progress Bar</span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setProgressVal((p) => Math.max(0, p - 10))}
                    >
                      -10%
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setProgressVal((p) => Math.min(100, p + 10))}
                    >
                      +10%
                    </Button>
                  </div>
                </div>
                <ProgressBar value={progressVal} showValue label="Extraction Pipeline Progress" />
              </div>

              <div className="space-y-2 pt-2 border-t border-slate-100">
                <span className="text-xs font-semibold text-slate-700">Skeleton Loading Placeholders</span>
                <div className="space-y-2 max-w-md">
                  <Skeleton height={20} width="80%" />
                  <Skeleton height={14} width="100%" />
                  <Skeleton height={14} width="60%" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Modal Demo */}
          <Modal
            isOpen={isModalOpen}
            onClose={() => setIsModalOpen(false)}
            title="Edit Baseline Details"
            description="Update metadata and version tag for this requirements baseline."
            footer={
              <>
                <Button variant="outline" size="sm" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    setIsModalOpen(false);
                    toast.success("Baseline details updated.");
                  }}
                >
                  Save Changes
                </Button>
              </>
            }
          >
            <div className="space-y-3 py-2">
              <Input label="Baseline Version" defaultValue="v1.4" />
              <Input label="Project Scope" defaultValue="Atlas Customer Portal" />
            </div>
          </Modal>

          {/* Confirm Dialog Demo */}
          <ConfirmDialog
            isOpen={isConfirmOpen}
            onClose={() => setIsConfirmOpen(false)}
            onConfirm={() => {
              setIsConfirmOpen(false);
              toast.error("Finding marked as dismissed.");
            }}
            title="Dismiss Finding F-001?"
            description="Dismissing will flag this issue as not a contradiction in the audit log."
            variant="warning"
            confirmLabel="Dismiss Finding"
          />

          {/* Drawer Demo */}
          <Drawer
            isOpen={isDrawerOpen}
            onClose={() => setIsDrawerOpen(false)}
            title="Requirement Details"
            subtitle="REQ-012 · Security Specification"
            footer={
              <Button variant="outline" size="sm" onClick={() => setIsDrawerOpen(false)}>
                Close Panel
              </Button>
            }
          >
            <div className="space-y-4 text-sm text-slate-700">
              <p>
                The system shall log users out after 5 minutes of inactivity.
              </p>
              <div className="text-xs text-slate-500">
                Section: §3.2 | Owner: Priya Shah | Last modified: 12 Oct 2026
              </div>
            </div>
          </Drawer>
        </div>
      )}
    </div>
  );
}
