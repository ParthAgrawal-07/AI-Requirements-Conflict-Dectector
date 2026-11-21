import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth";
import { useProjectRealtime } from "../../app/socket";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Tabs } from "../../components/Tabs";
import { useToast } from "../../components/Toast";
import { EditProposal } from "./ChangeEditor";
import { ChecksTab } from "./ChecksTab";
import { DiffView } from "./DiffView";
import { MergeBox } from "./MergeBox";
import { ReviewerList, ReviewsTab, type PendingComment } from "./ReviewsTab";
import {
  ACTIVE,
  STATUS_TEXT,
  STATUS_TONE,
  useChangeRequest,
  useChecks,
  useReviews,
  useUpdateChangeRequest,
  type ChangeRequest,
} from "./api";

/** One change request, like a pull request (US-33–US-35, interface design §7.2). */
export function ChangeRequestPage() {
  const { workspaceId = "", projectId = "", changeRequestId } = useParams();
  useProjectRealtime(projectId);
  const change = useChangeRequest(changeRequestId);
  // A failed background refresh keeps the last data on screen, so unsent comments survive it.
  if (!change.data) {
    if (change.isLoading) return <p className="page muted">Loading the change request…</p>;
    return <p className="page" role="alert">This change request could not be loaded.</p>;
  }
  return (
    <>
      {change.isError && (
        <p className="banner" role="alert">
          This change request could not be refreshed; what you see may be out of date.
        </p>
      )}
      <Detail change={change.data} workspaceId={workspaceId} projectId={projectId} />
    </>
  );
}

function Detail({ change, workspaceId, projectId }: { change: ChangeRequest; workspaceId: string; projectId: string }) {
  const { user } = useAuth();
  const { can } = usePermissions({ projectId });
  const notify = useToast();
  const reviews = useReviews(change.id);
  const checks = useChecks(change.id);
  const openDraft = useUpdateChangeRequest(change.id);
  const [tab, setTab] = useState("conversation");
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState<PendingComment[]>([]);
  const base = `/w/${workspaceId}/p/${projectId}`;
  const isProposer = change.proposer != null && change.proposer.id === user?.id;
  const active = ACTIVE.has(change.status);
  const canReview = can("rcr.review") && !isProposer && active && change.status !== "draft";
  const label = change.requirement.label ?? "The requirement";
  const risk = checks.data?.report?.risk_level;
  const failing = checks.data?.report?.checks.filter((c) => c.status === "fail" || c.status === "warning").length ?? 0;
  // A stale report is kept for reference; its risk and counts are not the current ones (US-34).
  const stale = checks.data?.state === "stale";

  return (
    <div className="page change-request-page">
      <p>
        <Link to={`${base}/changes`}>← Change requests</Link>
      </p>
      <header className="page-header">
        <h1>
          <span className="mono">{change.key}</span> {change.kind === "deprecate" ? "Deprecate" : "Change"}{" "}
          <span className="mono">{label}</span>
        </h1>
      </header>
      <p>
        <Badge tone={STATUS_TONE[change.status]}>{STATUS_TEXT[change.status]}</Badge>{" "}
        {risk && (
          <Badge tone={risk === "high" ? "conflict" : "neutral"}>
            Risk {risk[0].toUpperCase() + risk.slice(1)}
            {stale && " (out of date)"}
          </Badge>
        )}{" "}
        {change.requirement.is_protected && (
          <Badge tone="neutral" icon="⚑">
            Protected
          </Badge>
        )}{" "}
        <span className="muted small">
          Proposed by {change.proposer?.full_name ?? "a former member"} · base v{change.base_version} · revision{" "}
          {change.proposal_revision}
          {change.resolves.length > 0 && " · Resolves "}
        </span>
        {change.resolves.map((issue, index) => (
          <span key={issue.id} className="small">
            {index > 0 && ", "}
            <Link to={`${base}/issues/${issue.id}`}>{issue.key}</Link>
            {issue.status === "closed" && " (closed)"}
          </span>
        ))}
      </p>

      {change.status === "needs_update" || (active && change.base_version !== change.requirement.current_version) ? (
        <div className="banner banner-warning" role="status">
          <p>
            <strong>Needs update:</strong> {label} changed to v{change.requirement.current_version} after this request
            was written against v{change.base_version}. See the three-way view in Files changed.
          </p>
          {isProposer && !editing && (
            <Button size="sm" variant="primary" onClick={() => setEditing(true)}>
              Update request
            </Button>
          )}
        </div>
      ) : null}

      {change.status === "draft" && isProposer && (
        <div className="banner" role="status">
          <p>This is a draft: nobody is asked to review it yet.</p>
          <Button
            size="sm"
            variant="primary"
            loading={openDraft.isPending}
            onClick={() =>
              openDraft.mutate(
                { open: true },
                {
                  onSuccess: (next) => notify(`${next.key} is open for review`, "success"),
                  onError: (error) => notify(error instanceof ApiError ? error.message : "Could not open it", "error"),
                },
              )
            }
          >
            Open for review
          </Button>
        </div>
      )}

      {editing ? (
        <EditProposal change={change} onDone={() => setEditing(false)} />
      ) : (
        isProposer &&
        active && (
          <p>
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
              Edit proposal
            </Button>
          </p>
        )
      )}

      <div className="change-request-layout">
        <div>
          <Tabs
            label="Change request"
            selected={tab}
            onSelect={setTab}
            tabs={[
              { id: "conversation", label: pending.length ? `Conversation (${pending.length} pending)` : "Conversation" },
              { id: "diff", label: "Files changed" },
              {
                id: "checks",
                label: stale ? "Checks (out of date)" : failing ? `Checks (${failing} to look at)` : "Checks",
              },
            ]}
          >
            {tab === "conversation" && (
              <>
                <ReviewsTab change={change} reviews={reviews.data} canReview={canReview} pending={pending} onPendingChange={setPending} />
                <MergeBox change={change} canMerge={can("rcr.merge")} isProposer={isProposer} />
              </>
            )}
            {tab === "diff" && (
              <DiffView
                change={change}
                reviews={reviews.data?.reviews}
                onQuote={
                  canReview
                    ? (quote) => {
                        setPending([...pending, { ...quote, body: "" }]);
                        notify("Added to your review: write it under Conversation", "info");
                      }
                    : undefined
                }
              />
            )}
            {tab === "checks" && <ChecksTab changeRequestId={change.id} canRerun={can("rcr.review") && active} />}
          </Tabs>
        </div>
        <aside className="change-request-aside">
          <ReviewerList
            change={change}
            requests={reviews.data?.requests ?? []}
            workspaceId={workspaceId}
            canAdd={isProposer || can("rcr.merge")}
          />
          <section aria-label="Requirement">
            <h2 className="eyebrow">Requirement</h2>
            <p>
              <Link className="mono" to={`${base}/map?focus=${change.requirement.id}`}>
                {label}
              </Link>{" "}
              <span className="muted small">
                {change.requirement.state.replace("_", " ")} · v{change.requirement.current_version}
              </span>
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
