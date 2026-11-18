import { useState } from "react";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import {
  isProtected,
  PAIR_CATEGORIES,
  SINGLE_CATEGORIES,
  STATUS_LABEL,
  useFindings,
  useReviewFinding,
  type Finding,
  type FindingCategory,
  type ReviewAction,
} from "../findings/api";

export interface ReviewActionsProps {
  finding: Finding;
  projectId: string;
}

const LIVE = new Set(["flagged", "confirmed", "reclassified"]);
const DONE: Record<ReviewAction, string> = {
  confirm: "Finding accepted",
  dismiss: "Finding dismissed",
  merge: "Finding merged",
  reclassify: "Finding reclassified",
  reopen: "Finding reopened",
  escalate: "Finding escalated",
};

/** Review a finding (US-10, FR-18–FR-21): confirm, dismiss with a reason, merge into another
 *  finding of the same category, reclassify, reopen, or escalate. The AI's own category stays
 *  visible after a reclassification (FR-20). A finding about a protected requirement can only be
 *  acted on by a compliance reviewer (CR-19): the server enforces it, and the panel says so
 *  instead of offering buttons that would be refused. */
export function ReviewActions({ finding, projectId }: ReviewActionsProps) {
  const { can } = usePermissions({ projectId });
  const notify = useToast();
  const review = useReviewFinding(projectId);
  const [mode, setMode] = useState<"dismiss" | "reclassify" | "merge" | null>(null);
  const [reason, setReason] = useState("");
  const [category, setCategory] = useState<FindingCategory | "">("");
  const [target, setTarget] = useState("");
  const others = useFindings(projectId, {
    category: finding.category,
    limit: 50,
    offset: 0,
  });

  const guarded = isProtected(finding);
  const allowed = guarded ? can("protected.signoff") : can("finding.review");
  const live = LIVE.has(finding.status);
  const kinds = finding.requirements.length === 2 ? PAIR_CATEGORIES : SINGLE_CATEGORIES;

  const act = (action: ReviewAction, extra: { reason?: string; category?: FindingCategory; merge_into?: string } = {}) =>
    review.mutate(
      { findingId: finding.id, input: { action, ...extra } },
      {
        onSuccess: () => {
          setMode(null);
          setReason("");
          notify(DONE[action], "success");
        },
        onError: (error) => notify(error instanceof ApiError ? error.message : "Review failed", "error"),
      },
    );

  return (
    <section className="review-actions" aria-label="Review">
      <p>
        <Badge tone={finding.status === "dismissed" ? "neutral" : "info"}>{STATUS_LABEL[finding.status]}</Badge>
        {finding.ai_category && finding.ai_category !== finding.category && (
          <span className="muted small"> · AI said {finding.ai_category}</span>
        )}
        {finding.resolved && <Badge tone="approved">Resolved</Badge>}
      </p>
      {guarded && (
        <p className="muted small" role="note">
          <span aria-hidden="true">⚑ </span>Protected requirement: only a compliance reviewer can act on this finding.
        </p>
      )}
      {!allowed ? null : mode === null ? (
        <div className="row-actions">
          {(finding.status === "flagged" || finding.status === "reclassified") && (
            <Button size="sm" variant="primary" loading={review.isPending} onClick={() => act("confirm")}>
              Confirm
            </Button>
          )}
          {live && (
            <>
              <Button size="sm" onClick={() => setMode("dismiss")}>
                Dismiss…
              </Button>
              <Button size="sm" onClick={() => setMode("reclassify")}>
                Reclassify…
              </Button>
              <Button size="sm" onClick={() => setMode("merge")}>
                Merge…
              </Button>
              <Button size="sm" variant="ghost" onClick={() => act("escalate", { reason: reason || undefined })}>
                Escalate
              </Button>
            </>
          )}
          {!live && (
            <Button size="sm" variant="ghost" onClick={() => act("reopen")}>
              Reopen
            </Button>
          )}
        </div>
      ) : (
        <form
          className="form-stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (mode === "dismiss") act("dismiss", { reason: reason.trim() });
            if (mode === "reclassify" && category) act("reclassify", { category, reason: reason || undefined });
            if (mode === "merge" && target) act("merge", { merge_into: target, reason: reason || undefined });
          }}
        >
          {mode === "reclassify" && (
            <label>
              New category
              <select value={category} onChange={(e) => setCategory(e.target.value as FindingCategory)} required>
                <option value="">Choose…</option>
                {kinds
                  .filter((kind) => kind !== finding.category)
                  .map((kind) => (
                    <option key={kind} value={kind}>
                      {kind}
                    </option>
                  ))}
              </select>
            </label>
          )}
          {mode === "merge" && (
            <label>
              Merge into
              <select value={target} onChange={(e) => setTarget(e.target.value)} required>
                <option value="">Choose the finding that stays…</option>
                {(others.data?.items ?? [])
                  .filter((other) => other.id !== finding.id && LIVE.has(other.status))
                  .map((other) => (
                    <option key={other.id} value={other.id}>
                      {other.requirements.map((r) => r.label ?? "—").join(" ↔ ")} · {other.confidence_percent}%
                    </option>
                  ))}
              </select>
            </label>
          )}
          <label>
            {mode === "dismiss" ? "Why is it not a real issue?" : "Note (optional)"}
            <textarea
              rows={2}
              maxLength={2000}
              value={reason}
              required={mode === "dismiss"}
              minLength={mode === "dismiss" ? 3 : undefined}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <div className="row-actions">
            <Button type="submit" size="sm" variant="primary" loading={review.isPending}>
              {mode === "dismiss" ? "Dismiss" : mode === "merge" ? "Merge" : "Reclassify"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
