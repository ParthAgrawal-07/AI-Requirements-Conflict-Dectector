import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useBaselines } from "../baselines/api";
import {
  KIND_GROUPS,
  useChanges,
  useMarkSeen,
  useSummarise,
  type ChangeKind,
  type Summary,
  type SummaryStart,
} from "./changes";

export interface ChangesPanelProps {
  projectId: string;
  names: Map<string, string>;
  /** The time slider's point: only changes up to that map revision (null = now). */
  untilRevision: number | null;
  /** The node under the pointer on the map: the panel lists its changes while it is hovered. */
  hoveredNode: string | null;
  onSelect: (elementIds: string[]) => void;
}

function time(iso: string): string {
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** The Changes panel beside the map (Pranshu — US-55, FR-95, FR-96; interface design §9): every
 *  change as a sentence, newest first, filtered by person, kind and time; selecting one highlights
 *  its elements on the map; "Summarise changes since…" gives exact counts, the important changes
 *  and — on request — an AI paragraph, labelled AI, never part of the numbers. */
export function ChangesPanel({ projectId, names, untilRevision, hoveredNode, onSelect }: ChangesPanelProps) {
  const [actor, setActor] = useState("");
  const [group, setGroup] = useState("");
  const [since, setSince] = useState("");
  const [before, setBefore] = useState<string | undefined>(undefined);
  const kinds: ChangeKind[] = KIND_GROUPS.find((g) => g.label === group)?.kinds ?? [];
  const filters = useMemo(
    () => ({
      actor: actor || undefined,
      kinds,
      requirement: hoveredNode ?? undefined,
      since: since ? new Date(since).toISOString() : undefined,
      untilRevision,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [actor, group, hoveredNode, since, untilRevision],
  );
  const changes = useChanges(projectId, filters, before);
  const seen = useMarkSeen(projectId);
  useEffect(() => {
    setBefore(undefined); // a new filter starts from the newest change again
  }, [filters]);
  useEffect(() => {
    seen.mutate();
    // Opening the map counts as a visit, once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const items = changes.data?.items ?? [];
  return (
    <section className="changes-panel" aria-label="Changes panel">
      <h2 className="eyebrow">Changes</h2>
      <div className="changes-filters" role="group" aria-label="Filter changes">
        <label>
          <span className="sr-only">Person</span>
          <select className="select" value={actor} onChange={(e) => setActor(e.target.value)}>
            <option value="">Everyone</option>
            {[...names].map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Kind</span>
          <select className="select" value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">All kinds</option>
            {KIND_GROUPS.map((g) => (
              <option key={g.label} value={g.label}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
        <label className="small">
          Since{" "}
          <input type="date" className="input" value={since} onChange={(e) => setSince(e.target.value)} />
        </label>
      </div>
      {hoveredNode && <p className="muted small">Showing the changes of the requirement under the pointer.</p>}
      {untilRevision !== null && <p className="muted small">Up to the point chosen on the time slider.</p>}
      {changes.isError && <p role="alert">The change log could not be loaded.</p>}
      {!changes.isLoading && items.length === 0 && <p className="muted small">No changes match.</p>}
      <ol className="feed-list">
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className="feed-item"
              onClick={() => onSelect([...item.node_ids, ...item.edge_ids])}
            >
              <time className="muted small" dateTime={item.at}>
                {time(item.at)}
              </time>{" "}
              {item.sentence}
              {item.backfilled && <span className="muted small"> (from the audit log)</span>}
            </button>
          </li>
        ))}
      </ol>
      {changes.data?.next_before && (
        <Button size="sm" variant="ghost" onClick={() => setBefore(changes.data?.next_before ?? undefined)}>
          Older changes
        </Button>
      )}
      <SummaryBox projectId={projectId} />
    </section>
  );
}

function SummaryBox({ projectId }: { projectId: string }) {
  const baselines = useBaselines(projectId);
  const summarise = useSummarise(projectId);
  const notify = useToast();
  const [start, setStart] = useState("visit");
  const [date, setDate] = useState("");
  const [narrative, setNarrative] = useState(false);
  const result: Summary | undefined = summarise.data;

  const chosen = (): SummaryStart | null => {
    if (start === "visit") return { kind: "visit" };
    if (start === "date") return date ? { kind: "date", since: new Date(date).toISOString() } : null;
    return { kind: "baseline", baselineId: start };
  };
  const run = () => {
    const value = chosen();
    if (!value) return;
    summarise.mutate(
      { start: value, narrative },
      { onError: (error) => notify(error instanceof ApiError ? error.message : "Could not summarise", "error") },
    );
  };
  const copy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.markdown);
      notify("Summary copied as Markdown", "success");
    } catch {
      notify("Copy is not available in this browser", "error");
    }
  };

  return (
    <div className="summary-box">
      <div className="row-actions">
        <label className="small">
          Summarise changes since{" "}
          <select className="select" value={start} onChange={(e) => setStart(e.target.value)}>
            <option value="visit">my last visit</option>
            <option value="date">a date…</option>
            {(baselines.data ?? []).map((b) => (
              <option key={b.id} value={b.id}>
                baseline {b.label}
              </option>
            ))}
          </select>
        </label>
        {start === "date" && (
          <label>
            <span className="sr-only">Date</span>
            <input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
        )}
        <label className="small">
          <input type="checkbox" checked={narrative} onChange={(e) => setNarrative(e.target.checked)} /> add an AI
          paragraph
        </label>
        <Button size="sm" loading={summarise.isPending} onClick={run}>
          Summarise
        </Button>
      </div>
      {result && (
        <div aria-live="polite">
          <p className="small">
            <strong>Since {result.since_label}:</strong>{" "}
            {result.count_lines.length ? result.count_lines.join(" · ") : "no counted changes"}.
          </p>
          {result.highlights.length > 0 && (
            <ul className="small">
              {result.highlights.map((h) => (
                <li key={h.id}>{h.sentence}</li>
              ))}
            </ul>
          )}
          {result.narrative && (
            <p className="ai-paragraph small">
              <Badge tone="ai">AI</Badge> {result.narrative.text}
            </p>
          )}
          {narrative && result.narrative_status === "no_model" && (
            <p className="muted small">No AI model is configured: the counts and list above are complete.</p>
          )}
          {narrative && result.narrative_status === "unavailable" && (
            <p className="muted small">The AI paragraph is not available right now.</p>
          )}
          <Button size="sm" variant="ghost" onClick={copy}>
            Copy as Markdown
          </Button>
        </div>
      )}
    </div>
  );
}
