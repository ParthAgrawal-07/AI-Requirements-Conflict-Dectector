import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { RequirementState } from "../../api/types";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/Toast";
import { CATEGORY_ICONS, useFindings } from "../findings/api";
import { OwnerChip } from "../requirements/OwnerChip";
import { OwnershipRequestDialog } from "../requirements/OwnershipRequestDialog";
import { ProtectedBadge } from "../compliance/ProtectedBadge";
import { ProtectionControl } from "../compliance/ProtectionControl";
import { ReviewActions } from "../review/ReviewActions";
import { useMoveRequirement, useRequirement, type RequirementDetail } from "./api";

export interface NodeDrawerProps {
  projectId: string;
  requirementId: string | null;
  names: Map<string, string>;
  onClose: () => void;
}

const MOVE_LABEL: Record<RequirementState, string> = {
  Under_Review: "Start review",
  Approved: "Approve",
  Rejected: "Reject…",
  Implemented: "Mark implemented",
  Proposed: "Back to proposed",
  Deprecated: "Deprecate",
};

/** The requirement drawer opened from the map (US-14; interface design §6): the statement, owner
 *  and group (US-36), the lifecycle moves the member may make (US-37) with what still blocks
 *  approval, and its findings with the review actions (US-10). */
export function NodeDrawer({ projectId, requirementId, names, onClose }: NodeDrawerProps) {
  const requirement = useRequirement(requirementId);
  const data = requirement.data;
  return (
    <Drawer open={requirementId !== null} onClose={onClose} title={data?.source_req_id ?? "Requirement"}>
      {requirement.isLoading && <p className="muted">Loading…</p>}
      {requirement.isError && <p role="alert">This requirement could not be loaded.</p>}
      {data && <Detail detail={data} projectId={projectId} names={names} />}
    </Drawer>
  );
}

function Detail({ detail, projectId, names }: { detail: RequirementDetail; projectId: string; names: Map<string, string> }) {
  const { can } = usePermissions({ projectId });
  const { workspaceId = "" } = useParams();
  const notify = useToast();
  const move = useMoveRequirement(detail.requirement_id, projectId);
  const findings = useFindings(projectId, { requirement: detail.requirement_id, limit: 50, offset: 0 });
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [acceptRisk, setAcceptRisk] = useState(false);
  const [ownership, setOwnership] = useState(false);
  const highOpen = detail.readiness.open_high_findings.length > 0;

  const go = (state: RequirementState) =>
    move.mutate(
      {
        state,
        version: detail.current_version,
        reason: reason.trim() || undefined,
        accepted_risk: state === "Approved" && acceptRisk ? true : undefined,
      },
      {
        onSuccess: () => {
          setRejecting(false);
          setReason("");
          notify(`${detail.source_req_id ?? "Requirement"} is now ${state.replace("_", " ")}`, "success");
        },
        onError: (error) => notify(error instanceof ApiError ? error.message : "Could not change it", "error"),
      },
    );

  return (
    <>
      <p>
        <Badge tone={detail.state === "Approved" || detail.state === "Implemented" ? "approved" : "proposed"}>
          {detail.state.replace("_", " ")} · v{detail.current_version}
        </Badge>{" "}
        {detail.priority && <span className="muted small">{detail.priority.toUpperCase()}</span>}{" "}
        {detail.is_protected && <ProtectedBadge />}
      </p>
      <ProtectionControl
          projectId={projectId}
          requirementId={detail.requirement_id}
          label={detail.source_req_id}
          isProtected={detail.is_protected}
      />
      <blockquote className="requirement-quote">{detail.body}</blockquote>
      <p>
        <OwnerChip ownerName={detail.owner_name} group={detail.stakeholder_group} />{" "}
        <Button size="sm" variant="ghost" onClick={() => setOwnership(true)}>
          Ownership…
        </Button>{" "}
        {can("rcr.open") && (
          <Link className="btn btn-ghost btn-sm" to={`/w/${workspaceId}/p/${projectId}/changes/new?requirement=${detail.requirement_id}`}>
            Propose change
          </Link>
        )}
      </p>
      {detail.rationale && (
        <p>
          <strong>Rationale:</strong> {detail.rationale}
        </p>
      )}

      {detail.allowed_transitions.length > 0 && (
        <section aria-label="Lifecycle">
          <h3>Lifecycle</h3>
          {detail.allowed_transitions.includes("Approved") && (
            <ul className="readiness">
              <li>{detail.readiness.analysis_current ? "✓" : "✗"} Analysis has finished on this text</li>
              {detail.is_protected && <li>{detail.readiness.needs_signoff ? "✗" : "✓"} Compliance sign-off</li>}
              <li>
                {highOpen ? "⚠" : "✓"}{" "}
                {highOpen
                  ? `${detail.readiness.open_high_findings.length} High-severity finding open`
                  : "No High-severity finding open"}
              </li>
            </ul>
          )}
          {highOpen && detail.allowed_transitions.includes("Approved") && (
            <label className="small">
              <input type="checkbox" checked={acceptRisk} onChange={(e) => setAcceptRisk(e.target.checked)} /> Accept
              the risk (give a reason)
            </label>
          )}
          {(rejecting || acceptRisk) && (
            <label className="field">
              Reason
              <textarea rows={2} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          )}
          <div className="row-actions">
            {detail.allowed_transitions.map((state) => (
              <Button
                key={state}
                size="sm"
                variant={state === "Approved" ? "primary" : "secondary"}
                loading={move.isPending}
                onClick={() => (state === "Rejected" && !rejecting ? setRejecting(true) : go(state))}
              >
                {state === "Rejected" && rejecting ? "Reject" : MOVE_LABEL[state]}
              </Button>
            ))}
          </div>
        </section>
      )}

      <section aria-label="Findings">
        <h3>Findings</h3>
        {(findings.data?.items ?? []).length === 0 && (
          <p className="muted small">None open. Analysis can miss conflicts.</p>
        )}
        {(findings.data?.items ?? []).map((finding) => (
          <article key={finding.id} className="finding-card">
            <p>
              <Badge tone="conflict" icon={CATEGORY_ICONS[finding.category]}>
                {finding.category}
              </Badge>{" "}
              {finding.requirements.map((r) => r.label ?? "—").join(" ↔ ")} · {finding.confidence_percent}% confidence{" "}
              <Badge tone="ai">AI</Badge>
            </p>
            <p className="finding-explanation">{finding.explanation}</p>
            {finding.clarification && (
              <p>
                <strong>Clarification:</strong> {finding.clarification.question}
              </p>
            )}
            <ReviewActions finding={finding} projectId={projectId} />
          </article>
        ))}
      </section>

      {ownership && (
        <OwnershipRequestDialog
          open
          onClose={() => setOwnership(false)}
          projectId={projectId}
          requirement={detail}
          canRequest={can("req.propose")}
          canManage={can("baseline.manage")}
          names={names}
        />
      )}
    </>
  );
}
