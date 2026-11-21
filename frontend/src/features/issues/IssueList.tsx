import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth";
import { useProjectRealtime } from "../../app/socket";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { SourceBadge } from "../../components/SourceBadge";
import { useToast } from "../../components/Toast";
import { useRequirements } from "../requirements/api";
import { CLOSE_REASON_TEXT, sourceOf, useCreateIssue, useIssues, type IssueStatus } from "./api";
import { RaiseConcernDialog } from "./RaiseConcernDialog";

const PAGE = 25;
const STATUS_FILTERS: { value: IssueStatus | undefined; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "closed", label: "Closed" },
  { value: undefined, label: "All" },
];

/** The project's issues (US-52, Issues board): open first, by status, label and "assigned to
 *  me", each with who found it (AI, Rule or Person), its requirements and assignees. A member who
 *  may open issues opens one here or raises a concern (US-56). */
export function IssueList() {
  const { workspaceId = "", projectId = "" } = useParams();
  useProjectRealtime(projectId);
  const { user } = useAuth();
  const { can } = usePermissions({ projectId });
  const navigate = useNavigate();
  const [params] = useSearchParams(); // the dashboard's "closed" tile opens closed issues
  const [status, setStatus] = useState<IssueStatus | undefined>(
    params.get("status") === "closed" ? "closed" : "open",
  );
  const [mine, setMine] = useState(false);
  const [label, setLabel] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [raising, setRaising] = useState(false);
  const issues = useIssues(projectId, {
    status,
    label: label || undefined,
    assignee: mine ? user?.id : undefined,
    limit: PAGE,
    offset,
  });
  const page = issues.data;
  const base = `/w/${workspaceId}/p/${projectId}`;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Issues</h1>
        {can("issue.open") && (
          <div className="row-actions">
            <Button onClick={() => setRaising(true)}>Raise a concern</Button>
            <Button variant="primary" onClick={() => setCreating(true)}>
              New issue
            </Button>
          </div>
        )}
      </header>

      <div className="filters" role="group" aria-label="Filter issues">
        <div className="pill-group">
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              className="pill"
              aria-pressed={status === filter.value}
              onClick={() => {
                setStatus(filter.value);
                setOffset(0);
              }}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <button type="button" className="pill" aria-pressed={mine} onClick={() => setMine(!mine)}>
          Assigned to me
        </button>
        <label>
          <span className="sr-only">Label</span>
          <input
            className="input"
            placeholder="Label…"
            value={label}
            onChange={(e) => {
              setLabel(e.target.value.trim().toLowerCase());
              setOffset(0);
            }}
          />
        </label>
      </div>

      {issues.isLoading && <p className="muted">Loading issues…</p>}
      {issues.isError && <p role="alert">The issues could not be loaded.</p>}
      {page && page.items.length === 0 && (
        <p className="empty-state card">
          No issues here. Conflicts between owners open one by themselves; anyone can raise a concern.
        </p>
      )}
      <ul className="issue-list">
        {page?.items.map((issue) => {
          const source = sourceOf(issue);
          return (
            <li key={issue.id} className="card issue-row">
              <p className="issue-title">
                <Badge tone={issue.status === "open" ? "conflict" : "neutral"} icon={issue.status === "open" ? "●" : "✓"}>
                  {issue.status === "open" ? "Open" : "Closed"}
                </Badge>{" "}
                <span className="mono">{issue.key}</span>{" "}
                <Link to={`${base}/issues/${issue.id}`}>{issue.title}</Link> {source && <SourceBadge source={source} />}
              </p>
              <p className="muted small">
                {issue.requirements.map((r) => r.label ?? "—").join(", ")}
                {issue.assignees.length > 0 && ` · assigned to ${issue.assignees.map((a) => a.full_name).join(", ")}`}
                {issue.comment_count > 0 && ` · ${issue.comment_count} comment${issue.comment_count === 1 ? "" : "s"}`}
                {issue.close_reason && ` · ${CLOSE_REASON_TEXT[issue.close_reason]}`}
              </p>
              {issue.labels.length > 0 && (
                <p className="issue-labels">
                  {issue.labels.map((l) => (
                    <span key={l} className="label-chip">
                      {l}
                    </span>
                  ))}
                </p>
              )}
            </li>
          );
        })}
      </ul>
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

      {creating && (
        <NewIssueDrawer
          open
          onClose={() => setCreating(false)}
          projectId={projectId}
          onCreated={(id) => navigate(`${base}/issues/${id}`)}
        />
      )}
      {raising && (
        <RaiseConcernDialog
          open
          onClose={() => setRaising(false)}
          projectId={projectId}
          onRaised={(concern) => navigate(`${base}/issues/${concern.issue_id}`)}
        />
      )}
    </div>
  );
}

function NewIssueDrawer({
  open,
  onClose,
  projectId,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  onCreated: (issueId: string) => void;
}) {
  const notify = useToast();
  const create = useCreateIssue(projectId);
  const requirements = useRequirements(projectId, { limit: 200, offset: 0 });
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [labels, setLabels] = useState("");
  return (
    <Drawer open={open} onClose={onClose} title="New issue">
      <form
        className="form-stack"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate(
            {
              title: title.trim(),
              body: body.trim(),
              requirement_ids: picked,
              labels: labels.split(",").map((l) => l.trim()).filter(Boolean),
            },
            {
              onSuccess: (issue) => {
                notify(`${issue.key} opened`, "success");
                onCreated(issue.id);
              },
              onError: (error) => notify(error instanceof ApiError ? error.message : "Could not open it", "error"),
            },
          );
        }}
      >
        <label>
          Title
          <input required minLength={3} maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Requirements it is about
          <select
            multiple
            required
            value={picked}
            onChange={(e) => setPicked(Array.from(e.target.selectedOptions, (o) => o.value))}
          >
            {(requirements.data?.items ?? []).map((r) => (
              <option key={r.requirement_id} value={r.requirement_id}>
                {r.source_req_id ?? "Unnumbered"} — {r.body.length > 60 ? `${r.body.slice(0, 59)}…` : r.body}
              </option>
            ))}
          </select>
        </label>
        <label>
          Description
          <textarea rows={4} maxLength={10000} value={body} onChange={(e) => setBody(e.target.value)} />
        </label>
        <label>
          Labels <span className="muted small">(comma-separated)</span>
          <input value={labels} onChange={(e) => setLabels(e.target.value)} />
        </label>
        <div className="row-actions">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!title.trim() || picked.length === 0} loading={create.isPending}>
            Open issue
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
