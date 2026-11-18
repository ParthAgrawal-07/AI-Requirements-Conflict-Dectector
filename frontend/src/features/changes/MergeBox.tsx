import { useState } from "react";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import {
  ACTIVE,
  useAgreement,
  useCloseChangeRequest,
  useMerge,
  useWithdraw,
  type ChangeRequest,
  type Unmet,
} from "./api";

export interface MergeBoxProps {
  change: ChangeRequest;
  canMerge: boolean; // rcr.merge
  isProposer: boolean;
}

/** The agreement conditions in the order of interface design §8b. The server sends only the unmet
 *  ones (GET …/agreement); the met ones are ticked here so the box reads as a full checklist. */
const CONDITIONS: { code: string; text: string; applies?: (change: ChangeRequest) => boolean }[] = [
  { code: "needs_update", text: "Written against the current version" },
  { code: "checks_pending", text: "Checks are current for this revision" },
  { code: "approvals_missing", text: "Enough approvals on this revision" },
  { code: "reviewer_missing", text: "Owners and owners of conflicting requirements approved" },
  { code: "compliance_missing", text: "A compliance reviewer approved", applies: (c) => c.requirement.is_protected },
  { code: "changes_requested", text: "No reviewer asked for changes" },
  { code: "high_finding_open", text: "No High-severity finding open", applies: (c) => c.kind === "modify" },
];

/** Merge (US-35, FR-98): every condition with ✓ or ✗ and the server's own words, merge disabled
 *  until all pass — an open High finding can be accepted as a risk with a reason. A refused merge
 *  (409 ``merge_blocked``) lists the conditions the server found unmet. Members without the merge
 *  permission see the box greyed out with why (interface design §1, principle 8). */
export function MergeBox({ change, canMerge, isProposer }: MergeBoxProps) {
  const active = ACTIVE.has(change.status);
  const agreement = useAgreement(change.id, active);
  const merge = useMerge(change);
  const close = useCloseChangeRequest(change.id);
  const withdraw = useWithdraw(change.id);
  const notify = useToast();
  const [riskReason, setRiskReason] = useState("");
  const [closing, setClosing] = useState(false);
  const [closeReason, setCloseReason] = useState("");
  const [refused, setRefused] = useState<Unmet[]>([]);

  if (!active) {
    return (
      <section aria-label="Merge" className="merge-box merge-box-done">
        <p>
          {change.status === "merged"
            ? `Merged: ${change.requirement.label ?? "the requirement"} is now v${change.merged_version}.`
            : `${change.status === "withdrawn" ? "Withdrawn" : "Closed"} without merging.`}
        </p>
      </section>
    );
  }

  const unmet = agreement.data?.unmet ?? [];
  const unmetCodes = new Set(unmet.map((u) => u.code));
  const onlyRisk = unmet.length > 0 && unmet.every((u) => u.code === "high_finding_open");
  const ready = agreement.data?.mergeable === true || (onlyRisk && riskReason.trim().length >= 3);
  const known = new Set(CONDITIONS.map((c) => c.code));
  const fail = (error: unknown, fallback: string) => notify(error instanceof ApiError ? error.message : fallback, "error");

  return (
    <section aria-label="Merge" className="merge-box">
      <h2 className="eyebrow">Merge into the baseline</h2>
      {agreement.isLoading ? (
        <p className="muted small">Checking the agreement rules…</p>
      ) : (
        <ul className="readiness" aria-label="Agreement conditions">
          {unmet
            .filter((u) => !known.has(u.code))
            .map((u) => (
              <li key={u.code}>
                <span aria-hidden="true">✗</span> <span className="sr-only">Not met: </span>
                {u.message}
              </li>
            ))}
          {CONDITIONS.filter((c) => !c.applies || c.applies(change)).map((condition) => {
            const miss = unmet.find((u) => u.code === condition.code);
            return (
              <li key={condition.code}>
                <span aria-hidden="true">{miss ? "✗" : "✓"}</span>{" "}
                <span className="sr-only">{miss ? "Not met: " : "Met: "}</span>
                {miss ? miss.message : condition.text}
              </li>
            );
          })}
        </ul>
      )}

      {canMerge && unmetCodes.has("high_finding_open") && (
        <label className="field">
          Accept the open High-severity risk (reason)
          <textarea rows={2} maxLength={2000} value={riskReason} onChange={(e) => setRiskReason(e.target.value)} />
        </label>
      )}

      {refused.length > 0 && (
        <div role="alert" className="banner banner-warning">
          <p>
            <strong>The merge was refused:</strong>
          </p>
          <ul>
            {refused.map((u) => (
              <li key={u.code}>{u.message}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="row-actions">
        {isProposer && (
          <Button
            variant="ghost"
            loading={withdraw.isPending}
            onClick={() =>
              withdraw.mutate(undefined, {
                onSuccess: (next) => notify(`${next.key} withdrawn`, "success"),
                onError: (error) => fail(error, "Could not withdraw it"),
              })
            }
          >
            Withdraw
          </Button>
        )}
        {canMerge && !closing && (
          <Button variant="ghost" onClick={() => setClosing(true)}>
            Close without merging…
          </Button>
        )}
        <Button
          variant="primary"
          disabled={!canMerge || !ready}
          loading={merge.isPending}
          title={canMerge ? undefined : "You cannot merge change requests in this project"}
          onClick={() =>
            merge.mutate(onlyRisk ? riskReason.trim() : undefined, {
              onSuccess: (merged) => {
                setRefused([]);
                notify(`${merged.key} merged: ${merged.requirement.label ?? "the requirement"} is now v${merged.merged_version}`, "success");
              },
              onError: (error) => {
                if (error instanceof ApiError && error.code === "merge_blocked") {
                  setRefused(error.details.map((d) => ({ code: d.code ?? "unmet", message: d.message })));
                } else {
                  fail(error, "Could not merge it");
                }
              },
            })
          }
        >
          Merge into baseline
        </Button>
      </div>
      {!canMerge && <p className="muted small">You can review here; a member with the merge permission merges.</p>}

      {closing && (
        <form
          className="form-stack"
          aria-label="Close without merging"
          onSubmit={(event) => {
            event.preventDefault();
            close.mutate(closeReason.trim(), {
              onSuccess: (next) => {
                setClosing(false);
                notify(`${next.key} closed`, "success");
              },
              onError: (error) => fail(error, "Could not close it"),
            });
          }}
        >
          <label>
            Why is it not going in?
            <textarea rows={2} required minLength={3} maxLength={2000} value={closeReason} onChange={(e) => setCloseReason(e.target.value)} />
          </label>
          <div className="row-actions">
            <Button variant="ghost" onClick={() => setClosing(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" loading={close.isPending}>
              Close
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
