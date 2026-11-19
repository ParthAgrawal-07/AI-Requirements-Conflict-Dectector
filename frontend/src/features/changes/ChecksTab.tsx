import { ApiError } from "../../api/client";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useChecks, useRerunChecks, type Check, type CheckStatus, type DeltaGroup, type Report } from "./api";

export interface ChecksTabProps {
  changeRequestId: string;
  canRerun: boolean;
}

export const CHECK_ICON: Record<CheckStatus, string> = { pending: "…", pass: "✓", warning: "⚠", fail: "✗", info: "ⓘ" };
const CHECK_WORD: Record<CheckStatus, string> = {
  pending: "Pending",
  pass: "Passed",
  warning: "Warning",
  fail: "Failed",
  info: "Info",
};
const DELTA: { group: DeltaGroup; title: string }[] = [
  { group: "resolved", title: "Resolved" },
  { group: "new", title: "New" },
  { group: "still_open", title: "Still open" },
  { group: "must_rerun", title: "Must re-run before approval" },
];
const SOURCE: Record<string, string> = { ai: "AI", rule: "Rule", person: "Person" };

/** The consequence report (US-34, interface design §7.2 and §8b): the findings delta on top, then
 *  every check with an icon *and* a word, the risk with its reasons, the affected requirements and
 *  the AI summary — always labelled AI, and only shown when it agreed with the checks. */
export function ChecksTab({ changeRequestId, canRerun }: ChecksTabProps) {
  const checks = useChecks(changeRequestId);
  const rerun = useRerunChecks(changeRequestId);
  const notify = useToast();
  if (checks.isLoading) return <p className="muted">Loading the checks…</p>;
  if (checks.isError || !checks.data) return <p role="alert">The checks could not be loaded.</p>;
  const { state, stale_reasons, report } = checks.data;

  const rerunButton = canRerun && (
    <Button
      size="sm"
      loading={rerun.isPending}
      onClick={() =>
        rerun.mutate(undefined, {
          onSuccess: () => notify("Checks queued: they update here when done", "success"),
          onError: (error) => notify(error instanceof ApiError ? error.message : "Could not re-run the checks", "error"),
        })
      }
    >
      Re-run checks
    </Button>
  );

  if (state === "pending" || !report) {
    return (
      <section aria-label="Checks" className="checks-tab">
        <p className="muted" role="status">
          The checks are running on this revision. They usually finish within a minute.
        </p>
        {rerunButton}
      </section>
    );
  }

  return (
    <section aria-label="Checks" className="checks-tab">
      {state === "stale" && (
        <div className="banner banner-warning" role="status">
          <p>
            <strong>These results are out of date.</strong>{" "}
            {stale_reasons.length ? stale_reasons.join("; ") : "Something changed since they ran."}
          </p>
          {rerunButton}
        </div>
      )}
      <FindingsDelta report={report} />
      <ol className="check-list">
        {report.checks.map((check) => (
          <CheckRow key={check.key} check={check} />
        ))}
      </ol>
      {!report.checks.some((c) => c.status === "fail" || c.status === "warning") && (
        <p className="muted small">No issues detected by the checks — analysis can miss conflicts.</p>
      )}
      <p>
        <strong>Risk:</strong>{" "}
        {report.risk_level ? (
          <Badge tone={report.risk_level === "high" ? "conflict" : report.risk_level === "medium" ? "proposed" : "approved"}>
            {report.risk_level[0].toUpperCase() + report.risk_level.slice(1)}
          </Badge>
        ) : (
          <span className="muted">not rated</span>
        )}
        {report.risk_reasons.length > 0 && <span className="muted small"> — {report.risk_reasons.join("; ")}</span>}
      </p>
      <Affected report={report} />
      {report.narrative && (
        <section aria-label="AI summary" className="narrative">
          <h3 className="eyebrow">
            Summary <Badge tone="ai">AI</Badge>
          </h3>
          <p>{report.narrative.summary}</p>
          {report.narrative.points.length > 0 && (
            <ul>
              {report.narrative.points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          )}
          <p className="muted small">
            Written by {report.narrative.model} from the checks above; the checks are the record.
          </p>
        </section>
      )}
      {state === "done" && rerunButton && <div className="row-actions">{rerunButton}</div>}
    </section>
  );
}

function FindingsDelta({ report }: { report: Report }) {
  return (
    <section aria-label="Findings delta" className="findings-delta">
      <h3 className="eyebrow">Findings delta</h3>
      <ul className="delta-counts">
        {DELTA.map(({ group, title }) => (
          <li key={group}>
            <strong>{report.findings_delta[group]?.length ?? 0}</strong> {title}
          </li>
        ))}
      </ul>
      {DELTA.filter(({ group }) => (report.findings_delta[group]?.length ?? 0) > 0).map(({ group, title }) => (
        <details key={group} open={group === "new" || group === "must_rerun"}>
          <summary>{title}</summary>
          <ul className="delta-list">
            {report.findings_delta[group]?.map((entry, index) => (
              <li key={entry.finding_id ?? `${group}-${index}`}>
                <span className="mono">{entry.labels.join(" ↔ ")}</span> · {entry.category}{" "}
                <span className="muted small">({SOURCE[entry.source] ?? entry.source})</span>
                <br />
                <span className="small">{entry.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </section>
  );
}

function CheckRow({ check }: { check: Check }) {
  const labels = Array.isArray(check.details.labels) ? (check.details.labels as unknown[]).map(String) : [];
  return (
    <li className={`check check-${check.status}`}>
      <span className="check-icon" aria-hidden="true">
        {CHECK_ICON[check.status]}
      </span>
      <span>
        <strong>{check.title}</strong> <span className="sr-only">{CHECK_WORD[check.status]}: </span>
        <span className="muted small">{CHECK_WORD[check.status]}</span>
        <br />
        {check.message}
        {labels.length > 0 && (
          <details>
            <summary className="small">Which requirements</summary>
            <span className="mono small">{labels.join(", ")}</span>
          </details>
        )}
      </span>
    </li>
  );
}

function Affected({ report }: { report: Report }) {
  if (report.affected.length === 0) return <p className="muted small">No other requirement is affected.</p>;
  const direct = report.affected.filter((a) => a.depth === 1).length;
  return (
    <details className="affected">
      <summary>
        {report.affected.length} affected — {direct} direct, {report.affected.length - direct} two steps away
      </summary>
      <ul className="delta-list">
        {report.affected.map((affected) => (
          <li key={affected.requirement_id}>
            <span className="mono">{affected.label}</span>
            {affected.is_protected && <span aria-label="protected"> ⚑</span>} · {affected.reason}{" "}
            <span className="muted small">({affected.status})</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
