import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { WordDiff } from "../../components/WordDiff";
import { useMembers } from "../channels/api";
import { useIssues } from "../issues/api";
import { useRequirement, type RequirementDetail } from "../map/api";
import {
  useImpact,
  useOpenChangeRequest,
  useUpdateChangeRequest,
  type ChangeKind,
  type ChangeRequest,
} from "./api";

/** The change editor for a new request (US-33, interface design §7.1), opened from **Propose
 *  change** on a requirement or an issue: ``changes/new?requirement=<id>&resolves=<ISS number>``. */
export function ChangeEditor() {
  const { projectId = "" } = useParams();
  const [search] = useSearchParams();
  const requirementId = search.get("requirement");
  const requirement = useRequirement(requirementId);
  const { can, isLoading } = usePermissions({ projectId });

  if (!requirementId) {
    return (
      <p className="page" role="alert">
        Open the editor from a requirement: <strong>Propose change</strong> on the map or an issue.
      </p>
    );
  }
  if (requirement.isLoading || isLoading) return <p className="page muted">Loading the requirement…</p>;
  if (requirement.isError || !requirement.data) {
    return <p className="page" role="alert">This requirement could not be loaded.</p>;
  }
  if (!can("rcr.open")) {
    return <p className="page" role="alert">Your role cannot propose changes in this project.</p>;
  }
  const preselected = Number(search.get("resolves"));
  return (
    <div className="page change-editor-page">
      <NewChangeForm requirement={requirement.data} preselected={Number.isInteger(preselected) && preselected > 0 ? [preselected] : []} />
    </div>
  );
}

function NewChangeForm({ requirement, preselected }: { requirement: RequirementDetail; preselected: number[] }) {
  const { workspaceId = "", projectId = "" } = useParams();
  const navigate = useNavigate();
  const notify = useToast();
  const open = useOpenChangeRequest(requirement.requirement_id);
  const [kind, setKind] = useState<ChangeKind>("modify");
  const [text, setText] = useState(requirement.body);
  const [reason, setReason] = useState("");
  const [resolves, setResolves] = useState<number[]>(preselected);
  const issues = useIssues(projectId, { status: "open", requirement: requirement.requirement_id, limit: 50, offset: 0 });
  const label = requirement.source_req_id ?? "the requirement";
  const unchanged = kind === "modify" && text.trim() === requirement.body.trim();
  const base = `/w/${workspaceId}/p/${projectId}`;

  const submit = (draft: boolean) =>
    open.mutate(
      {
        kind,
        proposed_body: kind === "modify" ? text.trim() : undefined,
        reason: reason.trim(),
        base_version: requirement.current_version,
        resolves,
        draft,
      },
      {
        onSuccess: (change) => {
          notify(`${change.key} ${draft ? "saved as a draft" : "opened"}`, "success");
          navigate(`${base}/changes/${change.id}`);
        },
        onError: (error) => notify(error instanceof ApiError ? error.message : "Could not open the change request", "error"),
      },
    );

  return (
    <form
      className="form-stack change-editor"
      aria-label={`Propose a change to ${label}`}
      onSubmit={(event) => {
        event.preventDefault();
        submit(false);
      }}
    >
      <p>
        <Link to={`${base}/changes`}>← Change requests</Link>
      </p>
      <h1>
        Propose a change to <span className="mono">{label}</span>{" "}
        <span className="muted small">(base v{requirement.current_version})</span>
      </h1>
      <fieldset className="decision">
        <legend>Kind</legend>
        <label className="checkbox">
          <input type="radio" name="kind" checked={kind === "modify"} onChange={() => setKind("modify")} /> Modify
        </label>
        <label className="checkbox">
          <input type="radio" name="kind" checked={kind === "deprecate"} onChange={() => setKind("deprecate")} /> Deprecate
        </label>
      </fieldset>
      {kind === "modify" ? (
        <ProposalText current={requirement.body} text={text} onChange={setText} />
      ) : (
        <p className="muted">
          {label} leaves the baseline when this merges; its text stays in the version history.
        </p>
      )}
      <label>
        Reason (required)
        <textarea rows={2} required minLength={3} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {(issues.data?.items ?? []).length > 0 && (
        <fieldset>
          <legend>Resolves</legend>
          {(issues.data?.items ?? []).map((issue) => (
            <label key={issue.id} className="checkbox">
              <input
                type="checkbox"
                checked={resolves.includes(issue.number)}
                onChange={(e) =>
                  setResolves(e.target.checked ? [...resolves, issue.number] : resolves.filter((n) => n !== issue.number))
                }
              />
              <span className="mono">{issue.key}</span> {issue.title}
            </label>
          ))}
        </fieldset>
      )}
      <Preflight requirement={requirement} kind={kind} resolving={resolves.length} />
      <div className="row-actions">
        <Button disabled={unchanged || reason.trim().length < 3} loading={open.isPending} onClick={() => submit(true)}>
          Save as draft
        </Button>
        <Button type="submit" variant="primary" disabled={unchanged} loading={open.isPending}>
          Open change request
        </Button>
      </div>
      {unchanged && <p className="muted small">Change the text to propose a modification.</p>}
    </form>
  );
}

function ProposalText({ current, text, onChange }: { current: string; text: string; onChange: (text: string) => void }) {
  return (
    <>
      <label>
        Proposed text
        <textarea rows={4} required maxLength={4000} value={text} onChange={(e) => onChange(e.target.value)} />
      </label>
      <div>
        <span className="eyebrow">Diff</span>
        <WordDiff before={current} after={text} label="Your changes" />
      </div>
    </>
  );
}

/** Pre-flight (no LLM): what the change touches and who will be asked to review, before opening. */
function Preflight({ requirement, kind, resolving }: { requirement: RequirementDetail; kind: ChangeKind; resolving: number }) {
  const { workspaceId } = useParams();
  const impact = useImpact(requirement.requirement_id, kind);
  const members = useMembers(workspaceId);
  const names = new Map((members.data ?? []).map((m) => [m.user.id, m.user.full_name]));
  const affected = impact.data?.affected ?? [];
  const direct = affected.filter((a) => a.depth === 1).length;
  const reviewers = new Set([...(requirement.owner_id ? [requirement.owner_id] : []), ...(impact.data?.owners ?? [])]);

  return (
    <section aria-label="Pre-flight" className="preflight">
      <h2 className="eyebrow">Before you open it</h2>
      {impact.isLoading ? (
        <p className="muted small">Working out what this touches…</p>
      ) : (
        <ul className="readiness">
          {resolving > 0 && (
            <li>
              <span aria-hidden="true">✓</span> Resolves {resolving} issue{resolving === 1 ? "" : "s"}
            </li>
          )}
          <li>
            <span aria-hidden="true">ⓘ</span> {affected.length} affected requirement{affected.length === 1 ? "" : "s"} ({direct}{" "}
            direct, {affected.length - direct} two steps away)
          </li>
          {requirement.is_protected && (
            <li>
              <span aria-hidden="true">⚑</span> Protected: a compliance reviewer must approve
            </li>
          )}
          <li>
            <span aria-hidden="true">○</span> Reviewers (auto):{" "}
            {reviewers.size === 0
              ? "the project's reviewers"
              : [...reviewers].map((id) => names.get(id) ?? "a member").join(" · ")}
          </li>
        </ul>
      )}
      <p className="muted small">Full checks run once it is open; analysis can miss conflicts.</p>
    </section>
  );
}

export interface EditProposalProps {
  change: ChangeRequest;
  onDone: () => void;
}

/** The proposer edits an open request (a new revision: earlier approvals are dismissed, FR-98) or,
 *  when another request merged first, writes it against the current version ("Update request"). */
export function EditProposal({ change, onDone }: EditProposalProps) {
  const update = useUpdateChangeRequest(change.id);
  const notify = useToast();
  const rebase = change.base_version !== change.requirement.current_version;
  const [text, setText] = useState(change.proposed_body ?? "");
  const [reason, setReason] = useState(change.reason);
  const unchanged = change.kind === "modify" && text.trim() === change.current_body.trim();

  return (
    <form
      className="form-stack change-editor"
      aria-label="Edit the proposal"
      onSubmit={(event) => {
        event.preventDefault();
        update.mutate(
          {
            proposed_body: change.kind === "modify" ? text.trim() : undefined,
            reason: reason.trim(),
            rebase: rebase || undefined,
          },
          {
            onSuccess: (next) => {
              notify(`${next.key} is now revision ${next.proposal_revision}; the checks run again`, "success");
              onDone();
            },
            onError: (error) => notify(error instanceof ApiError ? error.message : "Could not save it", "error"),
          },
        );
      }}
    >
      {rebase && (
        <p className="muted small">
          This saves it against v{change.requirement.current_version}, the current text.
        </p>
      )}
      {change.kind === "modify" && <ProposalText current={change.current_body} text={text} onChange={setText} />}
      <label>
        Reason
        <textarea rows={2} required minLength={3} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="row-actions">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={unchanged} loading={update.isPending}>
          {rebase ? "Update request" : "Save new revision"}
        </Button>
      </div>
    </form>
  );
}
