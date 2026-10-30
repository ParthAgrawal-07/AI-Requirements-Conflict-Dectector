import React, { useState, useMemo } from "react";
import {
  PageHeader,
  DataTable,
  Column,
  Input,
  RequirementBadge,
  FilterDropdown,
  Button,
  SearchIcon,
  Drawer,
} from "../components/ui";

interface ExtractedRequirement {
  id: string; // e.g. "R12"
  title: string;
  statement: string;
  section: string;
  category: string;
  owner: string;
}

const mockExtractedReqs: ExtractedRequirement[] = [
  {
    id: "R08",
    title: "User report export",
    statement: "The system shall allow all authenticated users to export monthly summary reports in PDF format.",
    section: "§2.4",
    category: "Reporting",
    owner: "Ananya Roy",
  },
  {
    id: "R12",
    title: "Inactivity logout",
    statement: "The system shall log users out after 5 minutes of inactivity.",
    section: "§3.2",
    category: "Security requirements",
    owner: "Priya Shah",
  },
  {
    id: "R19",
    title: "Admin-only export access",
    statement: "Exporting system analytics and user reports shall be restricted to administrator accounts.",
    section: "§5.1",
    category: "Access Control",
    owner: "Marcus Vance",
  },
  {
    id: "R27",
    title: "Minimum session duration",
    statement: "The system shall maintain sessions for at least 30 minutes.",
    section: "§4.1",
    category: "Session requirements",
    owner: "Daniel Kim",
  },
  {
    id: "R33",
    title: "Log purging policy",
    statement: "To conserve disk storage, audit event logs shall be deleted 30 days after creation.",
    section: "§6.2",
    category: "Maintenance",
    owner: "Bansil Patel",
  },
  {
    id: "R41",
    title: "Regulatory compliance retention",
    statement: "All audit and access logs must be retained securely for a minimum of 12 months for compliance audit.",
    section: "§7.3",
    category: "Compliance",
    owner: "Priya Shah",
  },
  {
    id: "R46",
    title: "Immediate offline sync",
    statement: "The mobile app shall attempt synchronization immediately as changes occur regardless of network type.",
    section: "§8.1",
    category: "Mobile Client",
    owner: "Heet Shah",
  },
  {
    id: "R52",
    title: "Metered connection policy",
    statement: "Data synchronization exceeding 5MB shall only occur when connected to an unmetered Wi-Fi network.",
    section: "§8.7",
    category: "Network Policy",
    owner: "Heet Shah",
  },
  {
    id: "R61",
    title: "CSV export endpoint",
    statement: "The backend service shall output all tabular data exclusively as RFC 4180 compliant CSV.",
    section: "§9.3",
    category: "Backend API",
    owner: "Parth Agrawal",
  },
  {
    id: "R64",
    title: "Excel export format",
    statement: "Customer portal tables must support direct download as Microsoft Excel (.xlsx) files with preserved styling.",
    section: "§10.2",
    category: "Portal Requirements",
    owner: "Pranshu Chovatiya",
  },
  {
    id: "R72",
    title: "Storage timestamp timezone",
    statement: "All system events and database records must store timestamps in ISO 8601 UTC.",
    section: "§11.1",
    category: "Data Architecture",
    owner: "Bansil Patel",
  },
  {
    id: "R75",
    title: "UI timestamp display",
    statement: "User interface timestamps must be displayed according to the active user's local operating system timezone.",
    section: "§11.4",
    category: "UI Design",
    owner: "Dhvani Patel",
  },
];

export function RequirementsPage() {
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [selectedReq, setSelectedReq] = useState<ExtractedRequirement | null>(null);

  const filtered = useMemo(() => {
    return mockExtractedReqs.filter((r) => {
      if (search.trim()) {
        const q = search.toLowerCase();
        if (
          !r.id.toLowerCase().includes(q) &&
          !r.title.toLowerCase().includes(q) &&
          !r.statement.toLowerCase().includes(q)
        ) {
          return false;
        }
      }
      if (
        categoryFilter !== "all" &&
        r.category.toLowerCase() !== categoryFilter.toLowerCase()
      ) {
        return false;
      }
      return true;
    });
  }, [search, categoryFilter]);

  const columns: Column<ExtractedRequirement>[] = [
    {
      key: "id",
      header: "Req ID",
      sortable: true,
      className: "w-28",
      render: (item) => <RequirementBadge reqId={item.id} />,
    },
    {
      key: "title",
      header: "Title",
      sortable: true,
      className: "w-52 font-semibold text-slate-900",
    },
    {
      key: "statement",
      header: "Requirement Statement",
      render: (item) => (
        <span className="text-slate-700 text-sm">{item.statement}</span>
      ),
    },
    {
      key: "section",
      header: "Section",
      className: "w-24 text-slate-500 font-mono text-xs",
    },
    {
      key: "category",
      header: "Category",
      sortable: true,
      className: "w-36 text-slate-600 text-xs",
    },
    {
      key: "owner",
      header: "Owner",
      sortable: true,
      className: "w-32 text-slate-600 text-xs",
    },
    {
      key: "action",
      header: "",
      align: "right",
      className: "w-24",
      render: (item) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSelectedReq(item)}
          className="text-blue-600 hover:text-blue-700"
        >
          View
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[{ label: "Atlas Customer Portal" }, { label: "Requirements" }]}
        title="Requirements List"
        description="Extracted and catalogued requirements from the latest baseline document (v1.4)."
      />

      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="w-full md:w-96">
          <Input
            placeholder="Search requirements by ID or statement..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch("")}
            leftIcon={<SearchIcon size={16} />}
          />
        </div>

        <div className="flex items-center gap-2">
          <FilterDropdown
            label="Category"
            value={categoryFilter}
            options={[
              { value: "all", label: "All Categories" },
              { value: "security requirements", label: "Security" },
              { value: "session requirements", label: "Session" },
              { value: "reporting", label: "Reporting" },
              { value: "compliance", label: "Compliance" },
            ]}
            onChange={setCategoryFilter}
          />
        </div>
      </div>

      <DataTable
        data={filtered}
        columns={columns}
        pageSize={8}
        initialSortKey="id"
        footerNote="Requirements extracted via automated segmentation."
        onRowClick={(item) => setSelectedReq(item)}
      />

      {/* Requirement Details Drawer */}
      <Drawer
        isOpen={selectedReq !== null}
        onClose={() => setSelectedReq(null)}
        title={selectedReq?.title || "Requirement"}
        subtitle={`${selectedReq?.id} · ${selectedReq?.section}`}
        footer={
          <Button variant="outline" size="sm" onClick={() => setSelectedReq(null)}>
            Close Drawer
          </Button>
        }
      >
        {selectedReq && (
          <div className="space-y-4">
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide block mb-1">
                Full Statement
              </span>
              <p className="text-sm font-medium text-slate-900 leading-relaxed">
                {selectedReq.statement}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-white rounded-lg border border-slate-200">
                <span className="text-slate-400 block mb-0.5">Category</span>
                <span className="font-semibold text-slate-800">{selectedReq.category}</span>
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200">
                <span className="text-slate-400 block mb-0.5">Owner</span>
                <span className="font-semibold text-slate-800">{selectedReq.owner}</span>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
