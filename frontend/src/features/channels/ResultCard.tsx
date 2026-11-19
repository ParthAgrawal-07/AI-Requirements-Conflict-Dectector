import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { CATEGORY_ICONS } from "../findings/api";
import { RaiseConcernDialog } from "../issues/RaiseConcernDialog";
import type { Message } from "./api";
import { useAnalysisRun, type AnalysisRun, type RunFinding } from "./runs";

export const CLEAN_RESULT = "No issues detected by analysis — analysis can miss conflicts.";

/** The result card of a posted requirement's live analysis (US-31, interface design §10): each
 *  finding with its category, the other requirement, severity, confidence, rationale and
 *  clarification question; "waiting for budget"; or the clean result — which never says
 *  "verified" (DR-21) and lets a member raise a concern the analysis missed (US-56). Falls back
 *  to the card's plain text if the run cannot be read. */
export function ResultCard({ message }: { message: Message }) {
  const { workspaceId, projectId } = useParams();
  const runId = typeof message.payload?.run_id === "string" ? message.payload.run_id : null;
  const requirementId =
    typeof message.payload?.requirement_id === "string" ? message.payload.requirement_id : null;
  const { can } = usePermissions(projectId ? { projectId } : null);
  const [raising, setRaising] = useState(false);
  const run = useAnalysisRun(runId, message.edited_at ?? message.created_at);
  const mapLink =
    workspaceId && projectId && requirementId
      ? `/w/${workspaceId}/p/${projectId}/map?focus=${requirementId}`
      : null;

  return (
    <section className="result-card" aria-label="Analysis result">
      <header className="result-card-header">
        <Badge tone="ai">Analysis</Badge>
        {run.data && <RunStatusLine run={run.data} />}
      </header>
      {run.data ? (
        <RunBody
          run={run.data}
          subjectId={requirementId}
          onRaise={projectId && can("issue.open") ? () => setRaising(true) : null}
        />
      ) : (
        <p className="message-body">{message.body}</p>
      )}
      {mapLink && (
        <footer className="message-actions">
          <Link to={mapLink} className="btn btn-ghost btn-sm">
            View on map
          </Link>
        </footer>
      )}
      {raising && projectId && (
        <RaiseConcernDialog
          open
          onClose={() => setRaising(false)}
          projectId={projectId}
          requirementId={requirementId ?? undefined}
        />
      )}
    </section>
  );
}

function RunStatusLine({ run }: { run: AnalysisRun }) {
  if (run.status === "waiting_budget") {
    return (
      <Badge tone="info" icon="⏸">
        Waiting for budget
      </Badge>
    );
  }
  if (run.status !== "done") return <span className="muted small">Analysing…</span>;
  const seconds =
    run.finished_at !== null
      ? Math.round((Date.parse(run.finished_at) - Date.parse(run.created_at)) / 1000)
      : null;
  return seconds !== null ? <span className="muted small">{seconds} s</span> : null;
}

function RunBody({
  run,
  subjectId,
  onRaise,
}: {
  run: AnalysisRun;
  subjectId: string | null;
  onRaise: (() => void) | null;
}) {
  if (run.status === "waiting_budget") {
    return (
      <p className="message-body">
        This project&apos;s monthly analysis budget is used up. The analysis resumes automatically when
        budget is available.
      </p>
    );
  }
  const failed = run.pairs_failed + run.checks_failed;
  return (
    <div className="result-card-body">
      {run.error_message && (
        <p className="message-body error-text">Analysis could not finish: {run.error_message}</p>
      )}
      {run.findings.length > 0 && (
        <ul className="result-findings">
          {run.findings.map((finding) => (
            <FindingLine key={finding.id} finding={finding} subjectId={subjectId} />
          ))}
        </ul>
      )}
      {failed > 0 && (
        <p className="muted small">
          {failed} {failed === 1 ? "comparison" : "comparisons"} could not be completed; they are
          retried when the analysis runs again.
        </p>
      )}
      {run.status === "done" && run.findings.length === 0 && !run.error_message && (
        <p className="message-body">
          {CLEAN_RESULT}{" "}
          {onRaise && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onRaise}>
              Raise a concern
            </button>
          )}
        </p>
      )}
    </div>
  );
}

function FindingLine({ finding, subjectId }: { finding: RunFinding; subjectId: string | null }) {
  const others = finding.requirements.filter((r) => r.id !== subjectId);
  const relation =
    others.length > 0
      ? `${finding.category} with ${others.map((o) => o.label ?? "—").join(", ")}`
      : finding.category;
  return (
    <li className="result-finding">
      <Badge tone="conflict" icon={CATEGORY_ICONS[finding.category]}>
        {relation}
      </Badge>{" "}
      {finding.severity && <span className="mono small">{finding.severity}</span>}{" "}
      <span className="confidence">{finding.confidence_percent}% confidence</span>
      {finding.low_confidence && (
        <span className="low-confidence"> · low confidence — recommend manual review</span>
      )}
      <p className="finding-explanation">{finding.explanation}</p>
      {finding.clarification && (
        <p className="result-question">
          <strong>Clarification:</strong> {finding.clarification.question}
          {finding.clarification.answered && <span className="muted"> (answered)</span>}
        </p>
      )}
    </li>
  );
}
