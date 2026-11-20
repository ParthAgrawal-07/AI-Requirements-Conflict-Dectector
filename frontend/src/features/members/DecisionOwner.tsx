import { Link, useParams } from "react-router-dom";
import { useDecision, type Decidable } from "./decisionRules";

/** "Decides: Meera — rule Protected requirements" (US-57, interface design §8b), linking to the
 *  rules. Shown on every finding, issue and change request. */
export function DecisionOwner({ kind, id }: { kind: Decidable; id: string | undefined }) {
  const { workspaceId, projectId } = useParams();
  const decision = useDecision(kind, id);
  if (!decision.data) return null;
  return (
    <p className="decision-owner small">
      <span aria-hidden="true">⚖ </span>
      {decision.data.sentence}
      {workspaceId && projectId && (
        <>
          {" "}
          <Link to={`/w/${workspaceId}/p/${projectId}/settings/decision-rules`}>rules</Link>
        </>
      )}
    </p>
  );
}
