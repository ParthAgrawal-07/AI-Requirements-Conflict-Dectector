import { useEffect, useState } from "react";
import type { RequirementRead, RequirementState } from "../../api/types";
import { useAuth } from "../../app/auth";
import { Badge } from "../../components/Badge";
import type { BadgeTone } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useRequirements, type RequirementFilters } from "./api";

const PAGE_SIZE = 50;

type Filter = "all" | "Approved" | "Proposed" | "mine";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "Approved", label: "Approved" },
  { id: "Proposed", label: "Proposed" },
  { id: "mine", label: "Mine" },
];

const STATE_TONE: Record<RequirementState, BadgeTone> = {
  Proposed: "proposed",
  Under_Review: "proposed",
  Approved: "approved",
  Implemented: "approved",
  Rejected: "neutral",
  Deprecated: "neutral",
};

const ORIGIN_LABEL: Record<RequirementRead["origin"], string> = {
  document: "Document",
  post: "Post",
  change_request: "Change request",
};

export function StateBadge({ requirement }: { requirement: RequirementRead }) {
  const label = requirement.state.replace("_", " ");
  const version = requirement.state === "Approved" ? ` v${requirement.current_version}` : "";
  return (
    <Badge tone={STATE_TONE[requirement.state]}>
      {label}
      {version}
    </Badge>
  );
}

/** The requirements screen's table (US-04): printed ID, text, state, owner, origin, group,
 *  with search, state/origin filters and pages. Shows why it is empty when it is. */
export function RequirementsTable({
  projectId,
  extractionFailed = false,
}: {
  projectId: string;
  extractionFailed?: boolean;
}) {
  const { user } = useAuth();
  const [filter, setFilter] = useState<Filter>("all");
  const [origin, setOrigin] = useState<RequirementFilters["origin"]>(undefined);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setQ(search.trim()), 300); // don't query on every keystroke
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => setOffset(0), [filter, origin, q]);

  const filters: RequirementFilters = {
    q: q || undefined,
    state: filter === "Approved" || filter === "Proposed" ? filter : undefined,
    owner: filter === "mine" ? user?.id : undefined,
    origin,
    limit: PAGE_SIZE,
    offset,
  };
  const { data, isLoading, isError, error } = useRequirements(projectId, filters);
  const total = data?.total ?? 0;

  return (
    <section aria-label="Requirements">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div className="pill-group" role="group" aria-label="Filter by state">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className="pill"
              aria-pressed={filter === item.id}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <label className="visually-hidden" htmlFor="req-origin">
            Origin
          </label>
          <select
            id="req-origin"
            className="select"
            value={origin ?? ""}
            onChange={(event) =>
              setOrigin((event.target.value || undefined) as RequirementFilters["origin"])
            }
          >
            <option value="">Any origin</option>
            <option value="document">Document</option>
            <option value="post">Post</option>
            <option value="change_request">Change request</option>
          </select>
          <label className="visually-hidden" htmlFor="req-search">
            Search requirements
          </label>
          <input
            id="req-search"
            className="input"
            type="search"
            placeholder="Search ID or text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16, overflowX: "auto" }}>
        {isError ? (
          <p className="empty-state" role="alert">
            Could not load requirements: {error instanceof Error ? error.message : "error"}
          </p>
        ) : isLoading ? (
          <p className="empty-state">Loading requirements…</p>
        ) : total === 0 ? (
          <EmptyState filtered={Boolean(q || origin || filter !== "all")} failed={extractionFailed} />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Statement</th>
                <th scope="col">State</th>
                <th scope="col">Owner</th>
                <th scope="col">Origin</th>
                <th scope="col">Group</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((item) => (
                <tr key={item.requirement_id}>
                  <td className="mono">
                    {item.source_req_id ?? <span className="muted">—</span>}
                    {item.is_protected && (
                      <span title="Protected" aria-label="Protected">
                        {" "}
                        ⚑
                      </span>
                    )}
                  </td>
                  <td>
                    {item.body}
                    {item.needs_review && (
                      <div>
                        <Badge tone="info" icon="?" title={item.review_reasons.join(" ")}>
                          Check extraction
                        </Badge>
                      </div>
                    )}
                  </td>
                  <td>
                    <StateBadge requirement={item} />
                  </td>
                  <td>{item.owner_name ?? <span className="muted">Unassigned</span>}</td>
                  <td>{ORIGIN_LABEL[item.origin]}</td>
                  <td>{item.stakeholder_group ?? <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {total > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
          <span className="mono muted">
            Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <Button
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <Button
            size="sm"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      )}
    </section>
  );
}

function EmptyState({ filtered, failed }: { filtered: boolean; failed: boolean }) {
  if (failed) {
    return (
      <p className="empty-state" role="status">
        Extraction failed, so there are no requirements yet. The reason is shown on the
        document above; fix the file and upload it again.
      </p>
    );
  }
  if (filtered) {
    return <p className="empty-state">No requirements match these filters.</p>;
  }
  return (
    <p className="empty-state">
      No requirements yet. Upload an SRS to extract them, or wait for a running upload to finish.
    </p>
  );
}
