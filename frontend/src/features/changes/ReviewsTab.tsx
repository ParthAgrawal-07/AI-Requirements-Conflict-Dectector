import { useState } from "react";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import type { Quote } from "./DiffView";
import {
  useSubmitReview,
  type ChangeRequest,
  type ReviewDecision,
  type Reviews,
} from "./api";

export interface PendingComment extends Quote {
  body: string;
}

export interface ReviewsTabProps {
  change: ChangeRequest;
  reviews: Reviews | undefined;
  canReview: boolean; // rcr.review, not the proposer, the request is open for review
  pending: PendingComment[];
  onPendingChange: (pending: PendingComment[]) => void;
}

const DECISION_TEXT: Record<ReviewDecision, string> = {
  approve: "approved",
  request_changes: "requested changes",
  comment: "commented",
};
const DECISION_LABEL: Record<ReviewDecision, string> = {
  approve: "Approve",
  request_changes: "Request changes",
  comment: "Comment only",
};

function when(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

/** The conversation's review part (US-35, interface design §7.2): every review in time order —
 *  those given on an earlier revision or base version struck through as *dismissed* (FR-98) — and
 *  the review form: approve, request changes or comment, with the inline comments picked in the
 *  Files-changed tab. */
export function ReviewsTab({ change, reviews, canReview, pending, onPendingChange }: ReviewsTabProps) {
  const submit = useSubmitReview(change.id);
  const notify = useToast();
  const [decision, setDecision] = useState<ReviewDecision>("approve");
  const [rationale, setRationale] = useState("");
  const timeline = [...(reviews?.reviews ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at));

  return (
    <section aria-label="Reviews" className="reviews-tab">
      <ol className="comment-list">
        <li className="comment">
          <p className="muted small">
            <strong>{change.proposer?.full_name ?? "A former member"}</strong> opened this · {when(change.created_at)}
          </p>
          <p className="issue-body">{change.reason}</p>
        </li>
        {timeline.map((review) => (
          <li key={review.id} className={review.dismissed ? "comment dismissed" : "comment"}>
            <p className="muted small">
              <strong>{review.reviewer?.full_name ?? "A former member"}</strong>{" "}
              {review.dismissed ? <s>{DECISION_TEXT[review.decision]}</s> : DECISION_TEXT[review.decision]} revision{" "}
              {review.proposal_revision} · {when(review.created_at)}
              {review.dismissed && " · dismissed: the proposal or its base changed since"}
            </p>
            {review.rationale && <p>{review.rationale}</p>}
            {review.comments.length > 0 && (
              <p className="muted small">
                {review.comments.length} inline comment{review.comments.length === 1 ? "" : "s"} (Files changed)
              </p>
            )}
          </li>
        ))}
        {change.status === "merged" && change.merged_at && (
          <li className="comment">
            <p className="muted small">
              Merged as v{change.merged_version} · {when(change.merged_at)}
            </p>
          </li>
        )}
        {change.closed_at && change.status !== "merged" && (
          <li className="comment">
            <p className="muted small">
              {change.status === "withdrawn" ? "Withdrawn" : "Closed"} · {when(change.closed_at)}
              {change.close_reason && ` — ${change.close_reason}`}
            </p>
          </li>
        )}
      </ol>

      {canReview && (
        <form
          className="form-stack review-form"
          aria-label="Your review"
          onSubmit={(event) => {
            event.preventDefault();
            submit.mutate(
              {
                decision,
                rationale: rationale.trim() || undefined,
                comments: pending.map((p) => ({
                  field: "statement",
                  start_offset: p.start_offset,
                  end_offset: p.end_offset,
                  body: p.body,
                })),
              },
              {
                onSuccess: () => {
                  setRationale("");
                  onPendingChange([]);
                  notify(`Review sent on revision ${change.proposal_revision}`, "success");
                },
                onError: (error) => notify(error instanceof ApiError ? error.message : "Could not send the review", "error"),
              },
            );
          }}
        >
          <fieldset className="decision">
            <legend>Your review of revision {change.proposal_revision}</legend>
            {(Object.keys(DECISION_TEXT) as ReviewDecision[]).map((value) => (
              <label key={value} className="checkbox">
                <input type="radio" name="decision" value={value} checked={decision === value} onChange={() => setDecision(value)} />
                {DECISION_LABEL[value]}
              </label>
            ))}
          </fieldset>
          <label>
            {decision === "request_changes" ? "What should change?" : "Note (optional)"}
            <textarea
              rows={3}
              maxLength={4000}
              value={rationale}
              required={decision === "request_changes"}
              onChange={(e) => setRationale(e.target.value)}
            />
          </label>
          {pending.map((comment, index) => (
            <div key={`${comment.start_offset}-${index}`} className="pending-comment">
              <label>
                On <q className="mono">{comment.text}</q>
                <textarea
                  rows={2}
                  maxLength={2000}
                  required
                  value={comment.body}
                  onChange={(e) =>
                    onPendingChange(pending.map((p, i) => (i === index ? { ...p, body: e.target.value } : p)))
                  }
                />
              </label>
              <Button size="sm" variant="ghost" onClick={() => onPendingChange(pending.filter((_, i) => i !== index))}>
                Remove
              </Button>
            </div>
          ))}
          {pending.length === 0 && (
            <p className="muted small">Select words in Files changed to comment on them.</p>
          )}
          <div className="row-actions">
            <Button type="submit" variant="primary" loading={submit.isPending}>
              Send review
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
