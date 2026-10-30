# AI Requirements Conflict Detector (RCD) — Frontend Foundation

Sprint 1 Frontend Architecture and Reusable UI Component Library.  
Primary Owner: **Abhijeet** (`aprk05`), supporting UI library setup across team pods.

---

## 1. Overview & Visual Design System

This frontend foundation translates the project's visual identity (from `Findings List.pdf`, `Conflict Review.pdf`, and `Clarification.pdf`) into an enterprise SaaS interface built on React, TypeScript, Vite, and Tailwind CSS.

### Design Tokens
- **Brand / Accent**: SaaS Blue (`#2563eb` / `#1d4ed8` / `blue-600`)
- **Neutrals**: Tailwind Slate (`slate-50` through `slate-900`)
- **Severity Colors**:
  - `Critical`: Rose (`bg-rose-100 text-rose-800 border-rose-300`)
  - `High`: Red (`bg-red-50 text-red-700 border-red-200`)
  - `Medium`: Amber (`bg-amber-50 text-amber-700 border-amber-200`)
  - `Low`: Blue (`bg-blue-50 text-blue-700 border-blue-200`)
- **Status Colors**:
  - `Pending Review`: Soft Blue (`bg-blue-50 text-blue-700 border-blue-200`)
  - `Awaiting Clarification`: Soft Amber (`bg-amber-50 text-amber-700 border-amber-200`)
  - `Resolved`: Soft Emerald (`bg-emerald-50 text-emerald-700 border-emerald-200`)
  - `Dismissed`: Muted Slate (`bg-slate-100 text-slate-500 border-slate-200`)
  - `Accepted`: Teal (`bg-teal-50 text-teal-700 border-teal-200`)
- **Border Radius & Shadows**:
  - Cards & Modals: `rounded-xl` (`12px`) or `rounded-2xl` (`16px`), `shadow-sm`
  - Buttons & Inputs: `rounded-lg` (`8px`)
  - Badges & Pills: `rounded-md` (`6px`) or `rounded-full`

---

## 2. Directory Structure

```
frontend/
├── src/
│   ├── components/
│   │   └── ui/                     # Reusable UI component library
│   │       ├── Icons.tsx           # Accessible SVG icons (Lucide-style, zero runtime deps)
│   │       ├── Button.tsx          # Buttons with variants (primary, secondary, outline, danger, ghost), loading spinner
│   │       ├── Input.tsx           # Text/search inputs with label, helper, error, onClear, icons
│   │       ├── Textarea.tsx        # Multi-line input with draft badge, char counter, autosize
│   │       ├── Select.tsx          # Styled form dropdown select
│   │       ├── FilterDropdown.tsx  # Filter pill dropdown with active state (as seen on Findings List)
│   │       ├── Badge.tsx           # SeverityBadge, StatusBadge, CategoryBadge, RequirementBadge, SourceBadge
│   │       ├── ConfidenceBadge.tsx # AI confidence badge (pill, compact score, bar)
│   │       ├── Card.tsx            # Card container, Header, Title, Description, Content, Footer
│   │       ├── StatCard.tsx        # KPI cards with bold numbers, subtitles, and click handlers
│   │       ├── RequirementCard.tsx # Side-by-side requirement comparison card with accent bar & metadata
│   │       ├── AIExplanationCard.tsx # AI rationale box with sparkle icon, severity badge, confidence & callout
│   │       ├── Table.tsx           # Table primitives (Table, Header, Body, Row, Head, Cell)
│   │       ├── DataTable.tsx       # Full DataTable with sorting, pagination, and empty states
│   │       ├── Modal.tsx           # Accessible modal with keyboard Esc & backdrop dismiss
│   │       ├── ConfirmDialog.tsx   # Action confirmation modal (destructive/warning/info)
│   │       ├── Drawer.tsx          # Slide-out drawer panel
│   │       ├── Tabs.tsx            # Horizontal tab navigation
│   │       ├── Toast.tsx           # ToastProvider & useToast hook (success, error, warning, info)
│   │       ├── Loading.tsx         # Spinner, Skeleton, ProgressBar
│   │       ├── TopNav.tsx          # Application header with logo, workspace name, user avatar
│   │       ├── Sidebar.tsx         # Application sidebar with route links & badge counters
│   │       ├── PageHeader.tsx      # Reusable page header with breadcrumb trail and action buttons
│   │       ├── PageLayout.tsx      # Shared shell layout with TopNav, Sidebar, Content, and Footer
│   │       └── index.ts            # Central barrel export
│   ├── pages/
│   │   ├── FindingsListPage.tsx    # Findings List screen (Findings List.pdf)
│   │   ├── ConflictReviewPage.tsx  # Conflict Review screen (Conflict Review.pdf)
│   │   ├── ClarificationPage.tsx   # Clarification question & answer screen (Clarification.pdf)
│   │   ├── ComponentShowcasePage.tsx # Live interactive component playground
│   │   ├── UploadPage.tsx          # SRS Upload placeholder (Pranshu)
│   │   ├── RequirementsPage.tsx    # Requirements table placeholder (Pranshu)
│   │   ├── DashboardPage.tsx       # Analytics dashboard placeholder (Dhvani)
│   │   ├── GraphPage.tsx           # Dependency graph placeholder (Dhvani)
│   │   └── ReportsPage.tsx         # Report generator placeholder (Abhijeet)
│   ├── lib/
│   │   ├── api-client.ts           # Central API client
│   │   └── sampleData.ts           # Realistic sample findings (F-001 through F-006)
│   ├── App.tsx                     # Top-level application with routing and toast provider
│   ├── main.tsx                    # React DOM root entry
│   └── types.ts                    # Shared TypeScript domain models
└── tests/
    ├── components.test.tsx         # Unit tests for all UI library components
    ├── App.test.tsx                # End-to-end integration navigation tests
    ├── harness.test.tsx            # Testing library harness smoke tests
    └── test-utils.tsx              # Testing helpers
```

---

## 3. Component Usage Examples

### Button
```tsx
import { Button, CheckIcon } from "@/components/ui";

<Button variant="primary" size="md" leftIcon={<CheckIcon size={16} />}>
  Accept Conflict
</Button>

<Button variant="outline" size="sm" isLoading={isSaving}>
  Save Draft
</Button>
```

### Badges
```tsx
import { SeverityBadge, StatusBadge, RequirementBadge, ConfidenceBadge } from "@/components/ui";

<SeverityBadge severity="High" />
<StatusBadge status="Pending Review" />
<RequirementBadge reqId="R12" />
<ConfidenceBadge confidence={0.92} />
```

### DataTable with Sorting & Pagination
```tsx
import { DataTable, Column } from "@/components/ui";

const columns: Column<FindingDetail>[] = [
  { key: "id", header: "Finding ID", sortable: true },
  { key: "summary", header: "Summary" },
  { 
    key: "severity", 
    header: "Severity", 
    render: (item) => <SeverityBadge severity={item.severity} /> 
  },
];

<DataTable data={findings} columns={columns} pageSize={10} initialSortKey="id" />
```

### Toast Notifications
```tsx
import { useToast } from "@/components/ui";

function MyActionComponent() {
  const toast = useToast();
  
  const handleResolve = () => {
    toast.success("Conflict marked as resolved.", "Finding Resolved");
  };
}
```

### Confirmation Dialog
```tsx
import { ConfirmDialog } from "@/components/ui";

<ConfirmDialog
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onConfirm={handleDelete}
  title="Dismiss Finding F-001?"
  description="This action marks the finding as an expected non-conflict."
  variant="warning"
  confirmLabel="Dismiss Finding"
/>
```

---

## 4. Commands for Development & Testing

```bash
# Start development server
cd frontend
npm run dev

# Run TypeScript compile validation
npm run typecheck

# Run ESLint linter
npm run lint

# Run all automated tests (Vitest)
npm run test:run

# Build production bundle
npm run build
```
