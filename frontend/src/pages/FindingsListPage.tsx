import React, { useState, useMemo } from "react";
import {
  PageHeader,
  StatCard,
  Input,
  FilterDropdown,
  Button,
  DataTable,
  Column,
  SeverityBadge,
  StatusBadge,
  ConfidenceBadge,
  RequirementBadge,
  SearchIcon,
} from "../components/ui";
import { sampleFindings, FindingDetail } from "../lib/sampleData";

export interface FindingsListPageProps {
  onSelectFinding: (id: string) => void;
}

export function FindingsListPage({ onSelectFinding }: FindingsListPageProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState("all");

  const filteredFindings = useMemo(() => {
    return sampleFindings.filter((finding) => {
      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesId = finding.id.toLowerCase().includes(q);
        const matchesSummary = finding.summary.toLowerCase().includes(q);
        const matchesReqs = finding.requirements.some((r) =>
          r.toLowerCase().includes(q)
        );
        if (!matchesId && !matchesSummary && !matchesReqs) return false;
      }

      // Severity filter
      if (
        severityFilter !== "all" &&
        finding.severity.toLowerCase() !== severityFilter.toLowerCase()
      ) {
        return false;
      }

      // Status filter
      if (
        statusFilter !== "all" &&
        finding.status.toLowerCase() !== statusFilter.toLowerCase()
      ) {
        return false;
      }

      // Confidence filter
      if (confidenceFilter === "high" && finding.confidence < 0.8) return false;
      if (
        confidenceFilter === "medium" &&
        (finding.confidence < 0.7 || finding.confidence >= 0.8)
      )
        return false;
      if (confidenceFilter === "low" && finding.confidence >= 0.7) return false;

      return true;
    });
  }, [searchQuery, severityFilter, statusFilter, confidenceFilter]);

  const clearFilters = () => {
    setSearchQuery("");
    setSeverityFilter("all");
    setStatusFilter("all");
    setConfidenceFilter("all");
  };

  const hasActiveFilters =
    searchQuery.trim() !== "" ||
    severityFilter !== "all" ||
    statusFilter !== "all" ||
    confidenceFilter !== "all";

  const columns: Column<FindingDetail>[] = [
    {
      key: "id",
      header: "Finding ID",
      sortable: true,
      className: "font-mono font-medium text-slate-900 w-28",
    },
    {
      key: "requirements",
      header: "Requirements",
      render: (item) => (
        <div className="flex items-center gap-1.5 font-mono text-xs">
          {item.requirements.map((req, i) => (
            <React.Fragment key={req}>
              {i > 0 && <span className="text-slate-400 font-bold">·</span>}
              <RequirementBadge reqId={req} />
            </React.Fragment>
          ))}
        </div>
      ),
      className: "w-36",
    },
    {
      key: "summary",
      header: "Conflict summary",
      sortable: true,
      render: (item) => (
        <span className="font-medium text-slate-800 text-sm block max-w-xl truncate">
          {item.summary}
        </span>
      ),
    },
    {
      key: "severity",
      header: "Severity",
      sortable: true,
      render: (item) => <SeverityBadge severity={item.severity} />,
      className: "w-28",
    },
    {
      key: "confidence",
      header: "AI confidence",
      sortable: true,
      render: (item) => (
        <ConfidenceBadge
          confidence={item.confidence}
          variant="compact"
          className="font-semibold text-slate-800"
        />
      ),
      className: "w-28",
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      render: (item) => <StatusBadge status={item.status} />,
      className: "w-40",
    },
    {
      key: "actions",
      header: "Action",
      align: "right",
      render: (item) => (
        <Button
          variant="outline"
          size="sm"
          onClick={() => onSelectFinding(item.id)}
          className="bg-blue-50/50 text-blue-700 hover:bg-blue-100 hover:text-blue-800 border-blue-200"
        >
          Review Finding
        </Button>
      ),
      className: "w-36",
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: "Atlas Customer Portal" },
          { label: "Findings" },
        ]}
        title="Findings"
        description="Review possible requirement conflicts. AI findings support your judgment; they do not replace it."
      />

      {/* 4 KPI Cards matching Findings List.pdf */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          value="6"
          label="Total findings"
          description="Across 12 requirements"
          valueColor="text-slate-900"
        />
        <StatCard
          value="3"
          label="Pending review"
          description="Ready for assessment"
          valueColor="text-blue-600"
          onClick={() => setStatusFilter("pending review")}
          isSelected={statusFilter === "pending review"}
        />
        <StatCard
          value="2"
          label="High severity"
          description="Prioritize these findings"
          valueColor="text-slate-900"
          onClick={() => setSeverityFilter("high")}
          isSelected={severityFilter === "high"}
        />
        <StatCard
          value="1"
          label="Awaiting clarification"
          description="Owner response requested"
          valueColor="text-slate-900"
          onClick={() => setStatusFilter("awaiting clarification")}
          isSelected={statusFilter === "awaiting clarification"}
        />
      </div>

      {/* Search and Filters Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="w-full md:w-96">
          <Input
            placeholder="Search finding ID, requirement or keyword"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onClear={() => setSearchQuery("")}
            leftIcon={<SearchIcon size={16} />}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2.5 w-full md:w-auto">
          <FilterDropdown
            label="Severity"
            value={severityFilter}
            options={[
              { value: "all", label: "All" },
              { value: "high", label: "High" },
              { value: "medium", label: "Medium" },
              { value: "low", label: "Low" },
            ]}
            onChange={setSeverityFilter}
          />

          <FilterDropdown
            label="Status"
            value={statusFilter}
            options={[
              { value: "all", label: "All" },
              { value: "pending review", label: "Pending Review" },
              { value: "awaiting clarification", label: "Awaiting Clarification" },
              { value: "resolved", label: "Resolved" },
              { value: "dismissed", label: "Dismissed" },
            ]}
            onChange={setStatusFilter}
          />

          <FilterDropdown
            label="Confidence"
            value={confidenceFilter}
            options={[
              { value: "all", label: "All" },
              { value: "high", label: "High (>80%)" },
              { value: "medium", label: "Medium (70–80%)" },
              { value: "low", label: "Low (<70%)" },
            ]}
            onChange={setConfidenceFilter}
          />

          {hasActiveFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              className="text-blue-600 hover:text-blue-700 hover:bg-blue-50 font-medium"
            >
              Clear filters
            </Button>
          )}
        </div>
      </div>

      {/* Findings Table */}
      <DataTable
        data={filteredFindings}
        columns={columns}
        pageSize={10}
        initialSortKey="id"
        footerNote="Review Finding opens the evidence and reviewer actions."
      />
    </div>
  );
}
