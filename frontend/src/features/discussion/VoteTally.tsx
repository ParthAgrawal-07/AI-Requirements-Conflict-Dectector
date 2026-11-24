import { ApiError } from "../../api/client";
import { useParams } from "react-router-dom";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useVote, useVotes } from "./api";

export interface VoteTallyProps {
  changeRequestId: string;
}

/** Support and opposition on a change request, shown to its reviewers (US-53). Information only:
 *  a vote is not a review and never counts towards merging (DR-17). */
export function VoteTally({ changeRequestId }: VoteTallyProps) {
  const { projectId = "" } = useParams();
  const { can } = usePermissions(projectId ? { projectId } : null);
  const tally = useVotes("change-requests", changeRequestId);
  const vote = useVote("change-requests", changeRequestId);
  const notify = useToast();
  const data = tally.data;
  if (!data) return null;
  const fail = (error: unknown) => notify(error instanceof ApiError ? error.message : "Could not vote", "error");
  return (
    <p className="vote-tally small">
      <span>
        Stakeholders: ▲ {data.support} support · ▼ {data.oppose} oppose
      </span>{" "}
      <span className="muted">(not a review; votes never decide)</span>{" "}
      {can("req.vote") && (
        <>
          <Button size="sm" variant="ghost" aria-pressed={data.mine === "support"}
            onClick={() => vote.mutate(data.mine === "support" ? null : { stance: "support" }, { onError: fail })}>
            ▲ Support
          </Button>
          <Button size="sm" variant="ghost" aria-pressed={data.mine === "oppose"}
            onClick={() => vote.mutate(data.mine === "oppose" ? null : { stance: "oppose" }, { onError: fail })}>
            ▼ Oppose
          </Button>
        </>
      )}
    </p>
  );
}
