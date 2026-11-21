import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export type TimelineKind =
  | "post"
  | "version"
  | "state"
  | "analysis"
  | "finding"
  | "review"
  | "clarification"
  | "issue"
  | "change_request"
  | "merge"
  | "comment"
  | "owner"
  | "baseline"
  | "vote"
  | "link";

export interface TimelineEntry {
  at: string;
  kind: TimelineKind;
  title: string;
  actor_id: UUID | null;
  actor_name: string | null;
  link_type: "requirement" | "finding" | "issue" | "change_request" | "baseline" | "run" | null;
  link_id: UUID | null;
  detail: string | null;
}

export interface TimelineData {
  requirement_id: UUID;
  label: string | null;
  kinds: TimelineKind[];
  entries: TimelineEntry[];
}

const KIND_TEXT: Record<TimelineKind, string> = {
  post: "Posted",
  version: "Versions",
  state: "Lifecycle",
  analysis: "Analysis",
  finding: "Findings",
  review: "Reviews",
  clarification: "Questions",
  issue: "Issues",
  change_request: "Change requests",
  merge: "Merges",
  comment: "Comments",
  owner: "Owner",
  baseline: "Baselines",
  vote: "Votes",
  link: "Links",
};

export function useTimeline(requirementId: string, kind: TimelineKind | "") {
  return useQuery({
    queryKey: ["timeline", requirementId, kind],
    queryFn: () =>
      apiFetch<TimelineData>(`/requirements/${requirementId}/timeline`, { query: { kind: kind || undefined } }),
  });
}

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** One requirement's activity timeline (Pranshu — US-42 UI; API by Dhavni): posts, analysis,
 *  findings, questions, issues, change requests, reviews, merges, votes and versions, newest
 *  first, each linking to its detail; filter by kind. */
export function Timeline({ requirementId }: { requirementId: string }) {
  const { workspaceId = "", projectId = "" } = useParams();
  const [kind, setKind] = useState<TimelineKind | "">("");
  const timeline = useTimeline(requirementId, kind);
  const base = `/w/${workspaceId}/p/${projectId}`;
  const href = (entry: TimelineEntry): string | null => {
    if (!entry.link_id) return null;
    switch (entry.link_type) {
      case "finding":
        return `${base}/findings?finding=${entry.link_id}`;
      case "issue":
        return `${base}/issues/${entry.link_id}`;
      case "change_request":
        return `${base}/changes/${entry.link_id}`;
      case "baseline":
        return `${base}/baselines`;
      case "requirement":
        return `${base}/map?focus=${entry.link_id}`;
      default:
        return null;
    }
  };
  return (
    <section aria-label="Timeline" className="timeline">
      <div className="row-actions">
        <h3>Timeline</h3>
        <label className="small">
          <span className="sr-only">Show</span>
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value as TimelineKind | "")}>
            <option value="">Everything</option>
            {(timeline.data?.kinds ?? (Object.keys(KIND_TEXT) as TimelineKind[])).map((k) => (
              <option key={k} value={k}>
                {KIND_TEXT[k]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {timeline.isLoading && <p className="muted small">Loading…</p>}
      {timeline.isError && <p role="alert">The timeline could not be loaded.</p>}
      {timeline.data && timeline.data.entries.length === 0 && <p className="muted small">Nothing yet.</p>}
      <ol className="timeline-list">
        {(timeline.data?.entries ?? []).map((entry, index) => {
          const target = href(entry);
          return (
            <li key={`${entry.at}-${index}`} className={`timeline-${entry.kind}`}>
              <time className="muted small" dateTime={entry.at}>
                {when(entry.at)}
              </time>{" "}
              <span className="badge badge-neutral">
                <span className="badge-icon" aria-hidden="true">
                  •
                </span>
                {KIND_TEXT[entry.kind]}
              </span>{" "}
              {target ? <Link to={target}>{entry.title}</Link> : entry.title}
              {entry.actor_name && <span className="muted small"> · {entry.actor_name}</span>}
              {entry.detail && <div className="muted small">{entry.detail}</div>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
