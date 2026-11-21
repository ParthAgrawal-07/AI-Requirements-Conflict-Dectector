import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useProjectRealtime } from "../../app/socket";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { STATUS_TEXT, STATUS_TONE, useChangeRequests, type ChangeStatus } from "./api";

const PAGE = 25;
const FILTERS: { id: ChangeStatus | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "open", label: "Open" },
  { id: "needs_update", label: "Needs update" },
  { id: "approved", label: "Approved" },
  { id: "draft", label: "Drafts" },
  { id: "merged", label: "Merged" },
  { id: "closed", label: "Closed" },
];

/** The project's change requests, newest first (US-33). A new one starts from **Propose change**
 *  on a requirement (the map's drawer) or on an issue. */
export function ChangeRequestList() {
  const { workspaceId = "", projectId = "" } = useParams();
  useProjectRealtime(projectId);
  const [status, setStatus] = useState<ChangeStatus | "all">("open");
  const [offset, setOffset] = useState(0);
  const list = useChangeRequests(projectId, { status: status === "all" ? undefined : status, limit: PAGE, offset });
  const base = `/w/${workspaceId}/p/${projectId}`;
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Change requests</h1>
      </header>
      <p className="muted small">
        To propose one, open a requirement on the <Link to={`${base}/map`}>map</Link> or an{" "}
        <Link to={`${base}/issues`}>issue</Link> and choose <strong>Propose change</strong>.
      </p>
      <label>
        Status{" "}
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as ChangeStatus | "all");
            setOffset(0);
          }}
        >
          {FILTERS.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label}
            </option>
          ))}
        </select>
      </label>
      {list.isLoading && <p className="muted">Loading…</p>}
      {list.isError && <p role="alert">The change requests could not be loaded.</p>}
      {list.isSuccess && items.length === 0 && <p className="muted">No change requests here.</p>}
      <ul className="issue-list">
        {items.map((change) => (
          <li key={change.id} className="card issue-row">
            <p className="issue-title">
              <Link to={`${base}/changes/${change.id}`}>
                <span className="mono">{change.key}</span> {change.kind === "deprecate" ? "Deprecate" : "Change"}{" "}
                {change.requirement.label ?? "a requirement"}
              </Link>
              <Badge tone={STATUS_TONE[change.status]}>{STATUS_TEXT[change.status]}</Badge>
            </p>
            <p className="muted small">
              {change.reason.length > 120 ? `${change.reason.slice(0, 117)}…` : change.reason} · by{" "}
              {change.proposer?.full_name ?? "a former member"}
              {change.resolves.length > 0 && ` · Resolves ${change.resolves.map((i) => i.key).join(", ")}`}
            </p>
          </li>
        ))}
      </ul>
      {/* Also past the last page (an item closed under it): Previous must stay reachable. */}
      {(total > PAGE || offset > 0) && (
        <div className="row-actions">
          <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Previous
          </Button>
          <Button size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
