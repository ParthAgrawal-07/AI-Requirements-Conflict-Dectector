export interface FindingDetail {
  id: string; // e.g. "F-001"
  requirements: string[]; // ["R12", "R27"]
  summary: string;
  severity: "High" | "Medium" | "Low";
  confidence: number;
  status: "Pending Review" | "Awaiting Clarification" | "Resolved" | "Dismissed";
  title: string;
  detectedAt: string;
  baseline: string;
  explanation: string;
  recommendation: string;
  reviewerNotes?: string;
  reqA: {
    id: string;
    title: string;
    body: string;
    version: string;
    category: string;
    section: string;
    owner: string;
  };
  reqB: {
    id: string;
    title: string;
    body: string;
    version: string;
    category: string;
    section: string;
    owner: string;
  };
  clarification?: {
    question: string;
    answerDraft: string;
    owners: string[];
    history: {
      author: string;
      role: string;
      time: string;
      text: string;
    }[];
    stillOpen?: string;
  };
}

export const sampleFindings: FindingDetail[] = [
  {
    id: "F-001",
    requirements: ["R12", "R27"],
    summary:
      "Possible conflict: 5-minute inactivity logout vs. minimum 30-minute session",
    severity: "High",
    confidence: 0.92,
    status: "Pending Review",
    title: "Review possible session conflict",
    detectedAt: "12 Oct 2026, 09:20",
    baseline: "v1.4",
    explanation:
      'If both requirements describe the same authenticated session, logging out after 5 minutes of inactivity may prevent a session from lasting at least 30 minutes. However, "session" may refer to different layers, or R27 may allow inactivity-based logout.',
    recommendation:
      "Possible conflict, not a confirmed contradiction. Clarify the session definition and any inactivity exception before resolving.",
    reviewerNotes:
      "R12 and R27 may use different definitions of session. Confirm whether the 30-minute minimum applies to idle users and whether inactivity logout is an explicit exception.",
    reqA: {
      id: "R12",
      title: "Inactivity logout",
      body: "The system shall log users out after 5 minutes of inactivity.",
      version: "v1.4",
      category: "Security requirements",
      section: "§3.2",
      owner: "Priya Shah",
    },
    reqB: {
      id: "R27",
      title: "Minimum session duration",
      body: "The system shall maintain sessions for at least 30 minutes.",
      version: "v1.4",
      category: "Session requirements",
      section: "§4.1",
      owner: "Daniel Kim",
    },
    clarification: {
      question:
        "Do R12 and R27 refer to the same authenticated session? Must the session remain active for at least 30 minutes even when a user is inactive, or is logout after 5 minutes of inactivity an explicit exception to R27?",
      answerDraft: "",
      owners: ["Priya Shah", "Daniel Kim"],
      history: [
        {
          author: "Abhijeet",
          role: "Reviewer",
          time: "10:05",
          text: 'Does "session" refer to the same authenticated session in R12 and R27?',
        },
        {
          author: "Priya Shah",
          role: "Security owner",
          time: "10:18",
          text: "R12 concerns user inactivity in the authenticated session. Background requests should not reset the timer.",
        },
        {
          author: "Daniel Kim",
          role: "Session owner",
          time: "10:26",
          text: "R27 does not yet specify idle-user behavior. I need to confirm its intended scope; no inactivity exception is agreed.",
        },
      ],
      stillOpen: "Does the 30-minute minimum override inactivity logout?",
    },
  },
  {
    id: "F-002",
    requirements: ["R08", "R19"],
    summary: "All users can export reports vs. admin-only export access",
    severity: "High",
    confidence: 0.88,
    status: "Pending Review",
    title: "Access control export conflict",
    detectedAt: "12 Oct 2026, 09:20",
    baseline: "v1.4",
    explanation:
      "R08 states that any authenticated user may trigger PDF export of reports, whereas R19 limits all report generation and export to administrator role only.",
    recommendation:
      "Clarify permissions matrix: is regular user export scoped to personal data only?",
    reqA: {
      id: "R08",
      title: "User report export",
      body: "The system shall allow all authenticated users to export monthly summary reports in PDF format.",
      version: "v1.4",
      category: "Reporting",
      section: "§2.4",
      owner: "Ananya Roy",
    },
    reqB: {
      id: "R19",
      title: "Admin-only export access",
      body: "Exporting system analytics and user reports shall be restricted to administrator accounts.",
      version: "v1.4",
      category: "Access Control",
      section: "§5.1",
      owner: "Marcus Vance",
    },
  },
  {
    id: "F-003",
    requirements: ["R33", "R41"],
    summary: "Delete audit logs after 30 days vs. retain for one year",
    severity: "Medium",
    confidence: 0.84,
    status: "Awaiting Clarification",
    title: "Audit log retention mismatch",
    detectedAt: "12 Oct 2026, 09:20",
    baseline: "v1.4",
    explanation:
      "Storage optimization policy specifies purging audit logs older than 30 days, while compliance requirement specifies 365-day retention.",
    recommendation:
      "Reconcile data retention policy with regulatory compliance mandate.",
    reqA: {
      id: "R33",
      title: "Log purging policy",
      body: "To conserve disk storage, audit event logs shall be deleted 30 days after creation.",
      version: "v1.4",
      category: "Maintenance",
      section: "§6.2",
      owner: "Bansil Patel",
    },
    reqB: {
      id: "R41",
      title: "Regulatory compliance retention",
      body: "All audit and access logs must be retained securely for a minimum of 12 months for compliance audit.",
      version: "v1.4",
      category: "Compliance",
      section: "§7.3",
      owner: "Priya Shah",
    },
  },
  {
    id: "F-004",
    requirements: ["R46", "R52"],
    summary: "Immediate offline sync vs. sync only when connected",
    severity: "Medium",
    confidence: 0.79,
    status: "Pending Review",
    title: "Offline data synchronization policy",
    detectedAt: "12 Oct 2026, 09:20",
    baseline: "v1.4",
    explanation:
      "Requirement R46 requires optimistic background synchronization without waiting for high-bandwidth Wi-Fi, while R52 restricts background transfers over cellular.",
    recommendation:
      "Define sync queue behavior on metered vs unmetered connections.",
    reqA: {
      id: "R46",
      title: "Immediate offline sync",
      body: "The mobile app shall attempt synchronization immediately as changes occur regardless of network type.",
      version: "v1.4",
      category: "Mobile Client",
      section: "§8.1",
      owner: "Heet Shah",
    },
    reqB: {
      id: "R52",
      title: "Metered connection policy",
      body: "Data synchronization exceeding 5MB shall only occur when connected to an unmetered Wi-Fi network.",
      version: "v1.4",
      category: "Network Policy",
      section: "§8.7",
      owner: "Heet Shah",
    },
  },
  {
    id: "F-005",
    requirements: ["R61", "R64"],
    summary: "CSV-only export vs. mandatory XLSX support",
    severity: "Medium",
    confidence: 0.76,
    status: "Resolved",
    title: "Spreadsheet export format conflict",
    detectedAt: "12 Oct 2026, 09:20",
    baseline: "v1.4",
    explanation:
      "Core service requirement limited tabular output to CSV for simplicity, whereas customer portal specification mandates native Microsoft Excel (.xlsx) files.",
    recommendation:
      "Resolved: backend will generate CSV with server-side conversion pipeline for XLSX.",
    reqA: {
      id: "R61",
      title: "CSV export endpoint",
      body: "The backend service shall output all tabular data exclusively as RFC 4180 compliant CSV.",
      version: "v1.4",
      category: "Backend API",
      section: "§9.3",
      owner: "Parth Agrawal",
    },
    reqB: {
      id: "R64",
      title: "Excel export format",
      body: "Customer portal tables must support direct download as Microsoft Excel (.xlsx) files with preserved styling.",
      version: "v1.4",
      category: "Portal Requirements",
      section: "§10.2",
      owner: "Pranshu Chovatiya",
    },
  },
  {
    id: "F-006",
    requirements: ["R72", "R75"],
    summary: "UTC timestamps vs. local time on separate display views",
    severity: "Low",
    confidence: 0.67,
    status: "Dismissed",
    title: "Timestamp presentation format",
    detectedAt: "12 Oct 2026, 09:20",
    baseline: "v1.4",
    explanation:
      "One requirement specified UTC for consistency across distributed servers, while another asked for user-local timezone presentation on client views.",
    recommendation:
      "Dismissed as non-conflict: server stores in UTC, client renders in local timezone.",
    reqA: {
      id: "R72",
      title: "Storage timestamp timezone",
      body: "All system events and database records must store timestamps in ISO 8601 UTC.",
      version: "v1.4",
      category: "Data Architecture",
      section: "§11.1",
      owner: "Bansil Patel",
    },
    reqB: {
      id: "R75",
      title: "UI timestamp display",
      body: "User interface timestamps must be displayed according to the active user's local operating system timezone.",
      version: "v1.4",
      category: "UI Design",
      section: "§11.4",
      owner: "Dhvani Patel",
    },
  },
];
