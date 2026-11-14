import { useState } from "react";
import { useParams } from "react-router-dom";
import { useProjectRealtime } from "../../app/socket";
import { Button } from "../../components/Button";
import { useFindings, type FindingCategory } from "./api";
import { FindingCard } from "./FindingCard";
import { FindingDrawer } from "./FindingDrawer";

const CATEGORIES: FindingCategory[] = ["Conflicting", "Duplicate", "Dependent", "Ambiguous", "Incomplete"];
const PAGE = 20;

/** The project's findings (US-05, US-07): most confident first, filter by category or by low
 *  confidence, open one side by side. Reviewing (confirm, dismiss…) arrives with US-10 (S3). */
export function FindingsPage() {
  const { projectId = "" } = useParams();
  useProjectRealtime(projectId);
  const [category, setCategory] = useState<FindingCategory | undefined>();
  const [lowOnly, setLowOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const findings = useFindings(projectId, {
    category,
    low_confidence: lowOnly ? true : undefined,
    limit: PAGE,
    offset,
  });
  const page = findings.data;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Findings</h1>
          <p className="muted" style={{ margin: 0 }}>
            Found by AI analysis — analysis can miss issues, and people decide.
          </p>
        </div>
      </div>
      <div className="filters" role="group" aria-label="Filter findings">
        <label>
          Category{" "}
          <select
            value={category ?? ""}
            onChange={(event) => {
              setCategory((event.target.value || undefined) as FindingCategory | undefined);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            {CATEGORIES.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={(event) => {
              setLowOnly(event.target.checked);
              setOffset(0);
            }}
          />{" "}
          Only low confidence
        </label>
      </div>
      {findings.isLoading && <p className="muted">Loading findings…</p>}
      {findings.isError && <p role="alert">The findings could not be loaded.</p>}
      {page && page.items.length === 0 && (
        <p className="empty-state card">No findings yet. They appear here when an analysis finishes.</p>
      )}
      <div className="finding-list">
        {page?.items.map((finding) => (
          <FindingCard key={finding.id} finding={finding} onOpen={(f) => setOpen(f.id)} />
        ))}
      </div>
      {page && page.total > PAGE && (
        <nav className="pager" aria-label="Pages">
          <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Previous
          </Button>
          <span className="muted">
            {offset + 1}–{Math.min(offset + PAGE, page.total)} of {page.total}
          </span>
          <Button size="sm" disabled={offset + PAGE >= page.total} onClick={() => setOffset(offset + PAGE)}>
            Next
          </Button>
        </nav>
      )}
      <FindingDrawer findingId={open} onClose={() => setOpen(null)} />
    </div>
  );
}
