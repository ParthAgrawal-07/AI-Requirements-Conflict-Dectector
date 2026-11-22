import { useState } from "react";
import { WatchButton } from "../discussion/WatchButton";
import { SuggestionPanel } from "../findings/SuggestionPanel";
import { DecisionOwner } from "../members/DecisionOwner";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useProjectRealtime } from "../../app/socket";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { SourceBadge } from "../../components/SourceBadge";
import { useToast } from "../../components/Toast";
import { useMembers } from "../channels/api";
import {
  CLOSE_REASON_TEXT,
  sourceOf,
  useAddComment,
  useIssue,
  useIssueComments,
  useUpdateIssue,
  type Issue,
} from "./api";

function when(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

/** One issue (US-52, Issues board): what it is about, who found it and who is on it, its
 *  discussion, and — for whoever may — close, reopen, labels and assignees. An auto issue closes
 *  by itself when its finding is resolved or a change request that resolves it merges. */
export function IssuePage() {
  const { workspaceId = "", projectId = "", issueId } = useParams();
  useProjectRealtime(projectId);
  const issue = useIssue(issueId);
  if (issue.isLoading) return <p className="page muted">Loading the issue…</p>;
  if (issue.isError || !issue.data) return <p className="page" role="alert">This issue could not be loaded.</p>;
  return <IssueDetail issue={issue.data} workspaceId={workspaceId} projectId={projectId} />;
}

function IssueDetail({ issue, workspaceId, projectId }: { issue: Issue; workspaceId: string; projectId: string }) {
  const { can } = usePermissions({ projectId });
  const notify = useToast();
  const update = useUpdateIssue(issue.id, projectId);
  const source = sourceOf(issue);
  const base = `/w/${workspaceId}/p/${projectId}`;
  const fail = (error: unknown) => notify(error instanceof ApiError ? error.message : "Something went wrong", "error");

  return (
    <div className="page issue-page">
      <p>
        <Link to={`${base}/issues`}>← Issues</Link>
      </p>
      <header className="page-header">
        <h1>
          <span className="mono">{issue.key}</span> {issue.title}
        </h1>
        <WatchButton subject="issues" id={issue.id} />
      </header>
      <DecisionOwner kind="issues" id={issue.id} />
      <p>
        <Badge tone={issue.status === "open" ? "conflict" : "neutral"} icon={issue.status === "open" ? "●" : "✓"}>
          {issue.status === "open" ? "Open" : "Closed"}
        </Badge>{" "}
        {source && <SourceBadge source={source} />}{" "}
        <span className="muted small">
          {issue.author ? `Opened by ${issue.author.full_name}` : "Opened automatically"} · {when(issue.created_at)}
          {issue.close_reason && ` · Closed: ${CLOSE_REASON_TEXT[issue.close_reason]}`}
        </span>
      </p>
      {issue.body && <p className="issue-body">{issue.body}</p>}
      {issue.finding_id && issue.status === "open" && <SuggestionPanel findingId={issue.finding_id} />}

      <section aria-label="Requirements">
        <h2 className="eyebrow">Requirements</h2>
        <ul className="inline-list">
          {issue.requirements.map((r) => (
            <li key={r.id}>
              <Link className="mono" to={`${base}/map?focus=${r.id}`}>
                {r.label ?? "Unnumbered"}
              </Link>{" "}
              <span className="muted small">{r.state.replace("_", " ")}</span>
              {issue.status === "open" && can("rcr.open") && (
                <>
                  {" "}
                  <Link className="small" to={`${base}/changes/new?requirement=${r.id}&resolves=${issue.number}`}>
                    Propose change
                  </Link>
                </>
              )}
            </li>
          ))}
        </ul>
      </section>

      <People issue={issue} workspaceId={workspaceId} canManage={can("issue.manage")} onSave={(input) => update.mutate(input, { onError: fail })} />

      {can("issue.open") && (
        <div className="row-actions">
          <Button
            loading={update.isPending}
            onClick={() =>
              update.mutate(
                { status: issue.status === "open" ? "closed" : "open" },
                {
                  onSuccess: (next) => notify(`${next.key} ${next.status === "open" ? "reopened" : "closed"}`, "success"),
                  onError: fail,
                },
              )
            }
          >
            {issue.status === "open" ? "Close issue" : "Reopen issue"}
          </Button>
        </div>
      )}

      <Comments issueId={issue.id} canComment={can("issue.open")} />
    </div>
  );
}

function People({
  issue,
  workspaceId,
  canManage,
  onSave,
}: {
  issue: Issue;
  workspaceId: string;
  canManage: boolean;
  onSave: (input: { labels: string[]; assignee_ids: string[] }) => void;
}) {
  const members = useMembers(workspaceId);
  const [editing, setEditing] = useState(false);
  const [labels, setLabels] = useState(issue.labels.join(", "));
  const [assignees, setAssignees] = useState(issue.assignees.map((a) => a.id));
  if (!editing) {
    return (
      <section aria-label="Assignees and labels">
        <p>
          <strong>Assigned to:</strong>{" "}
          {issue.assignees.length ? issue.assignees.map((a) => a.full_name).join(", ") : <span className="muted">nobody</span>}
        </p>
        <p className="issue-labels">
          {issue.labels.map((l) => (
            <span key={l} className="label-chip">
              {l}
            </span>
          ))}
        </p>
        {canManage && (
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            Edit labels and assignees
          </Button>
        )}
      </section>
    );
  }
  return (
    <form
      className="form-stack"
      aria-label="Edit labels and assignees"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({ labels: labels.split(",").map((l) => l.trim()).filter(Boolean), assignee_ids: assignees });
        setEditing(false);
      }}
    >
      <label>
        Labels
        <input value={labels} onChange={(e) => setLabels(e.target.value)} />
      </label>
      <label>
        Assignees
        <select multiple value={assignees} onChange={(e) => setAssignees(Array.from(e.target.selectedOptions, (o) => o.value))}>
          {(members.data ?? []).map((m) => (
            <option key={m.user.id} value={m.user.id}>
              {m.user.full_name}
            </option>
          ))}
        </select>
      </label>
      <div className="row-actions">
        <Button variant="ghost" onClick={() => setEditing(false)}>
          Cancel
        </Button>
        <Button type="submit" variant="primary">
          Save
        </Button>
      </div>
    </form>
  );
}

function Comments({ issueId, canComment }: { issueId: string; canComment: boolean }) {
  const comments = useIssueComments(issueId);
  const add = useAddComment(issueId);
  const notify = useToast();
  const [body, setBody] = useState("");
  return (
    <section aria-label="Discussion">
      <h2 className="eyebrow">Discussion</h2>
      {(comments.data ?? []).length === 0 && <p className="muted small">No comments yet.</p>}
      <ol className="comment-list">
        {(comments.data ?? []).map((comment) => (
          <li key={comment.id} className="comment">
            <p className="muted small">
              <strong>{comment.author ? comment.author.full_name : "RCD"}</strong> · {when(comment.created_at)}
            </p>
            <p>{comment.body}</p>
          </li>
        ))}
      </ol>
      {canComment && (
        <form
          className="form-stack"
          onSubmit={(event) => {
            event.preventDefault();
            add.mutate(body.trim(), {
              onSuccess: () => setBody(""),
              onError: (error) => notify(error instanceof ApiError ? error.message : "Could not post it", "error"),
            });
          }}
        >
          <label>
            Comment
            <textarea rows={3} maxLength={10000} value={body} onChange={(e) => setBody(e.target.value)} />
          </label>
          <div className="row-actions">
            <Button type="submit" size="sm" disabled={!body.trim()} loading={add.isPending}>
              Comment
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
