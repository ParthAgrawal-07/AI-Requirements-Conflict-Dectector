import { Badge } from "../../components/Badge";
import { CATEGORY_ICONS, type Finding } from "./api";

export interface FindingCardProps {
  finding: Finding;
  onOpen?: (finding: Finding) => void;
}

/** A finding in a list (US-07): category badge, confidence 0–100%, the low-confidence marker,
 *  the explanation and the requirement IDs involved. "AI" says who produced it (DR-04). */
export function FindingCard({ finding, onOpen }: FindingCardProps) {
  const labels = finding.requirements.map((r) => r.label ?? "unnumbered requirement");
  return (
    <article className="card finding-card" aria-label={`${finding.category} finding about ${labels.join(" and ")}`}>
      <header className="finding-header">
        <Badge tone={finding.category === "Conflicting" ? "conflict" : "proposed"} icon={CATEGORY_ICONS[finding.category]}>
          {finding.category}
        </Badge>
        <span className="confidence" title="How sure the analysis is that the category is right">
          {finding.confidence_percent}% confidence
        </span>
        <Badge tone="ai">AI analysis</Badge>
        {finding.status !== "flagged" && <Badge tone="neutral">{finding.status}</Badge>}
      </header>
      {finding.low_confidence && (
        <p className="low-confidence" role="note">
          <span aria-hidden="true">⚠ </span>Low confidence — recommend manual review
        </p>
      )}
      <p className="finding-ids mono">{labels.join(finding.requirements.length === 2 ? " ↔ " : ", ")}</p>
      <p className="finding-explanation">{finding.explanation}</p>
      {onOpen && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onOpen(finding)}>
          View side by side
        </button>
      )}
    </article>
  );
}
