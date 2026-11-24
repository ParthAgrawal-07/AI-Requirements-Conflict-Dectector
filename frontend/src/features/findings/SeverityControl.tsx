import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { isProtected, SEVERITY_WORD, useSetSeverity, type Finding, type Severity } from "./api";
import { SeverityBadge } from "./SeverityBadge";

const LEVELS: Severity[] = ["low", "medium", "high"];

/** Severity in the finding drawer (Abhijeet — US-08): what is in force, what the system proposed
 *  and why, and — for a reviewer — an override with a reason. A finding about a protected
 *  requirement is changed only by a compliance reviewer, as with every review action. */
export function SeverityControl({ projectId, finding }: { projectId: string; finding: Finding }) {
  const { can } = usePermissions({ projectId });
  const notify = useToast();
  const update = useSetSeverity(projectId);
  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState<Severity>(finding.severity ?? "medium");
  const [reason, setReason] = useState("");
  const allowed = isProtected(finding) ? can("protected.signoff") : can("finding.review");
  const overridden = finding.severity_proposed && finding.severity_proposed !== finding.severity;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!reason.trim()) return;
    update.mutate(
      { findingId: finding.id, severity: level, reason: reason.trim() },
      {
        onSuccess: () => {
          notify(`Severity set to ${SEVERITY_WORD[level]}`, "success");
          setOpen(false);
          setReason("");
        },
        onError: (error) => notify(error instanceof ApiError ? error.message : "Could not change the severity", "error"),
      },
    );
  };

  return (
    <section className="severity-control" aria-label="Severity">
      <p>
        <SeverityBadge finding={finding} />
        {overridden && finding.severity_proposed && (
          <span className="muted small"> · the system proposed {SEVERITY_WORD[finding.severity_proposed]}</span>
        )}
        {allowed && (
          <>
            {" "}
            <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>
              Change severity…
            </Button>
          </>
        )}
      </p>
      {finding.severity_reason && <p className="muted small">Why: {finding.severity_reason}</p>}
      {open && (
        <form className="form-stack" onSubmit={submit} aria-label="Change severity">
          <fieldset className="pill-group">
            <legend className="small">Severity</legend>
            {LEVELS.map((value) => (
              <label key={value} className="pill">
                <input type="radio" name="severity" value={value} checked={level === value}
                  onChange={() => setLevel(value)} /> {SEVERITY_WORD[value]}
              </label>
            ))}
          </fieldset>
          <label>
            Reason (required, recorded)
            <textarea rows={2} maxLength={500} required value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="row-actions">
            <Button type="submit" size="sm" variant="primary" loading={update.isPending} disabled={!reason.trim()}>
              Save severity
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
