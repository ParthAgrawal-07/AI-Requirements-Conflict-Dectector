import { SEVERITY_WORD, type Finding, type Severity } from "./api";

const MARK: Record<Severity, string> = { high: "▲▲▲", medium: "▲▲", low: "▲" };
const SOURCE: Record<string, string> = {
  system: "proposed by the system",
  person: "set by the person who raised it",
  reviewer: "set by a reviewer",
};

/** Severity — how bad, beside confidence — how sure (Abhijeet — US-08, FR-42). A shape and a
 *  word, never colour alone; the source says whether a person has confirmed it. */
export function SeverityBadge({ finding }: { finding: Pick<Finding, "severity" | "severity_source"> }) {
  if (!finding.severity) return <span className="severity severity-unset muted small">Severity not set</span>;
  const source = finding.severity_source ? SOURCE[finding.severity_source] : null;
  return (
    <span className={`severity severity-${finding.severity}`} title={source ? `Severity ${source}` : undefined}>
      <span aria-hidden="true">{MARK[finding.severity]}</span> {SEVERITY_WORD[finding.severity]} severity
      {source && <span className="sr-only">, {source}</span>}
    </span>
  );
}
