import { Link, useParams } from "react-router-dom";
import { Badge } from "../../components/Badge";
import { Drawer } from "../../components/Drawer";
import { CATEGORY_ICONS, highlight, useFinding, type Finding, type FindingRequirement } from "./api";

export interface FindingDrawerProps {
  findingId: string | null;
  onClose: () => void;
}

function Source({ requirement }: { requirement: FindingRequirement }) {
  const { workspaceId, projectId } = useParams();
  if (requirement.origin === "post" && requirement.origin_message_id) {
    return <span className="muted">From a post in a channel</span>;
  }
  const where = [requirement.section_heading, requirement.location].filter(Boolean).join(" · ");
  return (
    <span className="muted">
      {where || "From an uploaded document"}
      {requirement.document_id && workspaceId && projectId && (
        <>
          {" · "}
          <Link to={`/w/${workspaceId}/p/${projectId}/requirements`}>Requirements</Link>
        </>
      )}
    </span>
  );
}

function RequirementPanel({ finding, requirement }: { finding: Finding; requirement: FindingRequirement }) {
  const spans = finding.evidence_spans.filter((span) => span.requirement_id === requirement.id);
  return (
    <section className="finding-side" aria-label={requirement.label ?? "Requirement"}>
      <h3 className="mono">
        {requirement.label ?? "Unnumbered"}{" "}
        {requirement.is_protected && (
          <Badge tone="neutral" icon="⚑">
            Protected
          </Badge>
        )}
      </h3>
      <p className="finding-text">
        {highlight(requirement.body, spans).map((part, index) =>
          part.marked ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>,
        )}
      </p>
      <Source requirement={requirement} />
    </section>
  );
}

/** A finding side by side (US-05, US-07): both requirements with the problem clause highlighted,
 *  the explanation, what is vague or missing, and how sure the analysis is. */
export function FindingDrawer({ findingId, onClose }: FindingDrawerProps) {
  const finding = useFinding(findingId);
  const data = finding.data;
  return (
    <Drawer open={findingId !== null} title={data ? `${data.category} finding` : "Finding"} onClose={onClose}>
      {finding.isLoading && <p className="muted">Loading…</p>}
      {finding.isError && <p role="alert">This finding could not be loaded.</p>}
      {data && (
        <>
          <p>
            <Badge tone={data.category === "Conflicting" ? "conflict" : "proposed"} icon={CATEGORY_ICONS[data.category]}>
              {data.category}
            </Badge>{" "}
            <strong>{data.confidence_percent}% confidence</strong> <Badge tone="ai">AI analysis</Badge>
          </p>
          {data.low_confidence && (
            <p className="low-confidence" role="note">
              <span aria-hidden="true">⚠ </span>Low confidence — recommend manual review
            </p>
          )}
          <div className={data.requirements.length === 2 ? "finding-sides two" : "finding-sides"}>
            {data.requirements.map((requirement) => (
              <RequirementPanel key={requirement.id} finding={data} requirement={requirement} />
            ))}
          </div>
          <h3>Why</h3>
          <p>{data.explanation}</p>
          {data.vague_terms.length > 0 && (
            <p>
              <strong>Vague wording:</strong> {data.vague_terms.map((term) => `“${term}”`).join(", ")}
            </p>
          )}
          {data.missing_information.length > 0 && (
            <>
              <strong>What is missing</strong>
              <ul>
                {data.missing_information.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          <p className="muted small">
            Produced by AI analysis{data.context_version ? ` with project context v${data.context_version}` : ""}
            {data.prompt_version ? ` · prompts ${data.prompt_version}` : ""}. People decide what to do with it.
          </p>
        </>
      )}
    </Drawer>
  );
}
