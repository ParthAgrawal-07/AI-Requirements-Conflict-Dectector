import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../app/auth";
import { useProjectRealtime } from "../../app/socket";
import { Button } from "../../components/Button";
import { useProjectDashboard, type Counts, type DashboardFilters } from "./api";

const SOURCE_LABEL: Record<string, string> = { ai: "AI", rule: "Rule", person: "Person" };
const STATUS_LABEL: Record<string, string> = {
  flagged: "Open",
  confirmed: "Accepted",
  dismissed: "Dismissed",
  merged: "Merged",
  reclassified: "Reclassified",
};

interface TileProps {
  title: string;
  counts: Counts;
  label?: (key: string) => string;
  /** Where each number leads (FR-28): the list, filtered to exactly what was counted. */
  href?: (key: string) => string | null;
}

/** One card of numbers. Each number is a link to the filtered list it counts. */
function Tile({ title, counts, label = (key) => key, href }: TileProps) {
  const entries = Object.entries(counts);
  return (
    <section className="tile" aria-label={title}>
      <h2 className="tile-title">{title}</h2>
      {entries.length === 0 ? (
        <p className="muted small">None</p>
      ) : (
        <dl className="tile-counts">
          {entries.map(([key, count]) => {
            const to = href?.(key);
            return (
              <div key={key} className="tile-row">
                <dt>{label(key)}</dt>
                <dd>{to && count > 0 ? <Link to={to}>{count}</Link> : count}</dd>
              </div>
            );
          })}
        </dl>
      )}
    </section>
  );
}

/** Insights › Dashboard (US-13, interface design §12): findings, requirements, change requests
 *  and issues, filtered by requirement fields; the numbers equal the lists they open. */
export function DashboardPage() {
  const { workspaceId = "", projectId = "" } = useParams();
  const { user } = useAuth();
  useProjectRealtime(projectId);
  const [filters, setFilters] = useState<DashboardFilters>({});
  const [defaulted, setDefaulted] = useState(false);
  const board = useProjectDashboard(projectId, filters);
  const data = board.data;
  const base = `/w/${workspaceId}/p/${projectId}`;

  // NFR-16: start on the view that suits the role (the server suggests it), once.
  useEffect(() => {
    if (!defaulted && data) {
      setDefaulted(true);
      if (data.suggested_filters.owner) setFilters({ owner: data.suggested_filters.owner });
    }
  }, [data, defaulted]);

  const set = (change: Partial<DashboardFilters>) =>
    setFilters((current) => {
      const next = { ...current, ...change };
      for (const key of Object.keys(next) as (keyof DashboardFilters)[]) {
        if (!next[key]) delete next[key];
      }
      return next;
    });

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Insights</h1>
          <p className="muted" style={{ margin: 0 }}>
            Counts of what analysis, rules and people found — analysis can miss issues.
          </p>
        </div>
        <Link to="ai-feedback">AI feedback →</Link>
      </header>

      <div className="filters" role="group" aria-label="Filter the dashboard">
        <label>
          <input
            type="checkbox"
            checked={filters.owner === user?.id}
            onChange={(event) => set({ owner: event.target.checked ? user?.id : undefined })}
          />{" "}
          My requirements
        </label>
        <label>
          Type{" "}
          <select
            value={filters.req_type ?? ""}
            onChange={(event) => set({ req_type: (event.target.value || undefined) as DashboardFilters["req_type"] })}
          >
            <option value="">All</option>
            <option value="functional">Functional</option>
            <option value="non_functional">Non-functional</option>
            <option value="constraint">Constraint</option>
          </select>
        </label>
        <label>
          Priority{" "}
          <select
            value={filters.priority ?? ""}
            onChange={(event) => set({ priority: (event.target.value || undefined) as DashboardFilters["priority"] })}
          >
            <option value="">All</option>
            <option value="must">Must</option>
            <option value="should">Should</option>
            <option value="could">Could</option>
            <option value="wont">Won&rsquo;t</option>
          </select>
        </label>
        <label>
          Group{" "}
          <input
            value={filters.group ?? ""}
            placeholder="e.g. Security"
            onChange={(event) => set({ group: event.target.value || undefined })}
          />
        </label>
        {Object.keys(filters).length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setFilters({})}>
            Clear filters
          </Button>
        )}
      </div>

      {board.isError && <p role="alert">The dashboard could not be loaded.</p>}
      {data && (
        <div className="tiles">
          <Tile
            title={`Findings (${data.findings.total})`}
            counts={data.findings.by_category}
            href={(key) => `${base}/findings?category=${encodeURIComponent(key)}`}
          />
          <Tile
            title="Findings by severity"
            counts={data.findings.by_severity}
            label={(key) => (key === "unset" ? "Not assessed" : key[0].toUpperCase() + key.slice(1))}
            href={(key) => (key === "unset" ? null : `${base}/findings?severity=${key}`)}
          />
          <Tile
            title="Findings by review"
            counts={data.findings.by_status}
            label={(key) => STATUS_LABEL[key] ?? key}
            href={(key) => `${base}/findings?status=${key}`}
          />
          <Tile
            title="Found by"
            counts={data.findings.by_source}
            label={(key) => SOURCE_LABEL[key] ?? key}
            href={(key) => `${base}/findings?source=${key}`}
          />
          <Tile
            title={`Requirements (${data.requirements.total})`}
            counts={data.requirements.by_state}
            label={(key) => key.replace("_", " ")}
            href={(key) => `${base}/requirements?state=${key}`}
          />
          <Tile
            title={`Open change requests (${data.change_requests.open})`}
            counts={data.change_requests.by_risk}
            label={(key) => (key === "unknown" ? "Checks not run" : `${key[0].toUpperCase()}${key.slice(1)} risk`)}
            href={() => `${base}/changes`}
          />
          <Tile
            title="Issues"
            counts={{ open: data.issues.open, closed: data.issues.closed, "opened automatically, open": data.issues.auto_open }}
            label={(key) => key[0].toUpperCase() + key.slice(1)}
            href={(key) => `${base}/issues${key === "closed" ? "?status=closed" : ""}`}
          />
        </div>
      )}
    </div>
  );
}
