import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useGraph } from "../map/api";
import {
  LINK_WORDS,
  useAddComment,
  useAddLink,
  useComments,
  useRemoveLink,
  useSocial,
  useVote,
  type LinkKind,
  type Stance,
} from "./api";
import { WatchButton } from "./WatchButton";

export interface DiscussionPanelProps {
  projectId: string;
  requirementId: string;
  label: string | null;
}

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** The requirement's discussion in the drawer (Madhav — US-53): support or oppose with a reason,
 *  watch, the links people made, and a comment thread separate from channel chat. Votes are
 *  shown as information only — they never decide (DR-17). */
export function DiscussionPanel({ projectId, requirementId, label }: DiscussionPanelProps) {
  const social = useSocial(requirementId);
  const [open, setOpen] = useState(false);
  const data = social.data;
  return (
    <section aria-label="Discussion" className="discussion">
      <h3>Discussion</h3>
      {social.isError && <p role="alert">The discussion could not be loaded.</p>}
      {data && (
        <>
          <Votes projectId={projectId} requirementId={requirementId} />
          <p>
            <WatchButton subject="requirements" id={requirementId} />
          </p>
          <Links projectId={projectId} requirementId={requirementId} label={label} />
          <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Hide comments" : `Comments (${data.comments})`}
          </Button>
          {open && <Thread projectId={projectId} requirementId={requirementId} />}
        </>
      )}
    </section>
  );
}

function Votes({ projectId, requirementId }: { projectId: string; requirementId: string }) {
  const { can } = usePermissions({ projectId });
  const social = useSocial(requirementId);
  const vote = useVote("requirements", requirementId);
  const notify = useToast();
  const [reason, setReason] = useState("");
  const tally = social.data?.votes;
  if (!tally) return null;
  const cast = (stance: Stance | null) =>
    vote.mutate(stance ? { stance, reason: reason.trim() || undefined } : null, {
      onSuccess: () => setReason(""),
      onError: (error) => notify(error instanceof ApiError ? error.message : "Could not vote", "error"),
    });
  return (
    <div className="votes">
      <p>
        <span aria-label={`${tally.support} support, ${tally.oppose} oppose`}>
          ▲ {tally.support} support · ▼ {tally.oppose} oppose
        </span>{" "}
        <span className="muted small">(shown to whoever decides; votes never change a state)</span>
      </p>
      {tally.votes.some((v) => v.reason) && (
        <ul className="vote-reasons small" aria-label="Reasons">
          {tally.votes
            .filter((v) => v.reason)
            .map((v) => (
              <li key={v.user_id}>
                {v.stance === "support" ? "▲" : "▼"} {v.user_name ?? "A former member"}: {v.reason}
              </li>
            ))}
        </ul>
      )}
      {can("req.vote") && (
        <div className="row-actions">
          <label className="sr-only" htmlFor={`vote-reason-${requirementId}`}>
            Reason for your vote (optional)
          </label>
          <input
            id={`vote-reason-${requirementId}`}
            placeholder="Reason (optional)"
            maxLength={1000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <Button size="sm" aria-pressed={tally.mine === "support"} loading={vote.isPending}
            onClick={() => cast("support")}>
            ▲ Support
          </Button>
          <Button size="sm" aria-pressed={tally.mine === "oppose"} loading={vote.isPending}
            onClick={() => cast("oppose")}>
            ▼ Oppose
          </Button>
          {tally.mine && (
            <Button size="sm" variant="ghost" onClick={() => cast(null)}>
              Withdraw
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function Links({ projectId, requirementId, label }: DiscussionPanelProps) {
  const { can } = usePermissions({ projectId });
  const social = useSocial(requirementId);
  const graph = useGraph(projectId);
  const add = useAddLink(requirementId, projectId);
  const remove = useRemoveLink(requirementId, projectId);
  const notify = useToast();
  const [target, setTarget] = useState("");
  const [kind, setKind] = useState<LinkKind>("depends_on");
  const links = social.data?.links ?? [];
  const others = (graph.data?.nodes ?? []).filter((n) => n.id !== requirementId && n.label);
  const fail = (error: unknown) => notify(error instanceof ApiError ? error.message : "Could not save the link", "error");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!target) return;
    add.mutate({ target_id: target, kind }, { onSuccess: () => setTarget(""), onError: fail });
  };

  return (
    <div className="links">
      <h4>Links</h4>
      {links.length === 0 && <p className="muted small">No links yet.</p>}
      <ul aria-label="Links" className="link-list">
        {links.map((link) => (
          <li key={link.id}>
            <Badge tone="neutral" icon="⇢">
              Person
            </Badge>{" "}
            {link.direction === "outgoing"
              ? `${label ?? "This"} ${LINK_WORDS[link.kind]} ${link.target_label ?? "a requirement"}`
              : `${link.source_label ?? "A requirement"} ${LINK_WORDS[link.kind]} ${label ?? "this one"}`}
            {link.created_by_name && <span className="muted small"> · {link.created_by_name}</span>}
            {can("req.link") && (
              <Button size="sm" variant="ghost" aria-label={`Remove link ${link.source_label ?? ""} ${LINK_WORDS[link.kind]} ${link.target_label ?? ""}`}
                onClick={() => remove.mutate(link, { onError: fail })}>
                Remove
              </Button>
            )}
          </li>
        ))}
      </ul>
      {can("req.link") && (
        <form className="row-actions" onSubmit={submit} aria-label="Add a link">
          <label>
            <span className="sr-only">Relation</span>
            <select value={kind} onChange={(e) => setKind(e.target.value as LinkKind)}>
              <option value="depends_on">depends on</option>
              <option value="refines">refines</option>
              <option value="related_to">is related to</option>
            </select>
          </label>
          <label>
            <span className="sr-only">Other requirement</span>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose a requirement…</option>
              {others.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.label}
                </option>
              ))}
            </select>
          </label>
          <Button size="sm" type="submit" disabled={!target} loading={add.isPending}>
            Link
          </Button>
        </form>
      )}
    </div>
  );
}

function Thread({ projectId, requirementId }: { projectId: string; requirementId: string }) {
  const { can } = usePermissions({ projectId });
  const comments = useComments(requirementId);
  const add = useAddComment(requirementId);
  const notify = useToast();
  const [body, setBody] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!body.trim()) return;
    add.mutate(
      { body: body.trim() },
      {
        onSuccess: () => setBody(""),
        onError: (error) => notify(error instanceof ApiError ? error.message : "Could not post it", "error"),
      },
    );
  };
  return (
    <div className="thread">
      {comments.isLoading && <p className="muted">Loading…</p>}
      <ol aria-label="Comments" className="comment-list">
        {(comments.data ?? []).map((c) => (
          <li key={c.id}>
            <p className="small">
              <strong>{c.author_name ?? "A former member"}</strong>{" "}
              <span className="muted">{when(c.created_at)}</span>
            </p>
            <p>{c.body}</p>
          </li>
        ))}
      </ol>
      {can("req.comment") && (
        <form onSubmit={submit}>
          <label className="field">
            Add a comment
            <textarea rows={2} maxLength={5000} value={body} onChange={(e) => setBody(e.target.value)} />
          </label>
          <Button size="sm" type="submit" disabled={!body.trim()} loading={add.isPending}>
            Comment
          </Button>
        </form>
      )}
    </div>
  );
}
