import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { ApiError, apiFetch } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { Tabs } from "../../components/Tabs";
import { useToast } from "../../components/Toast";
import { useProject } from "../projects/api";
import { DecisionRulesTab } from "./DecisionRulesTab";

// API by Heet (US-06): GET /projects/{p}/thresholds/preview, POST /projects/{p}/reanalyse;
// the values are saved with PATCH /projects/{p} (Parth). Key: ["threshold-preview", p, s, c].

interface PairExample {
  a_label: string | null;
  b_label: string | null;
  similarity: number;
  finding: string | null;
  found_by: string | null;
}

interface ThresholdPreview {
  similarity: {
    threshold: number;
    current: number;
    pairs_above: number;
    pairs_compared: number;
    above: PairExample[];
    below: PairExample[];
    truncated: boolean;
  };
  confidence: { threshold: number; current: number; confident: number; low_confidence: number };
}

const PREVIEW_DEBOUNCE_MS = 400;

function usePreview(projectId: string, similarity: number, confidence: number) {
  return useQuery({
    queryKey: ["threshold-preview", projectId, similarity, confidence],
    queryFn: () =>
      apiFetch<ThresholdPreview>(`/projects/${projectId}/thresholds/preview`, { query: { similarity, confidence } }),
    placeholderData: keepPreviousData,
  });
}

function Examples({ title, rows }: { title: string; rows: PairExample[] }) {
  return (
    <div>
      <h3 className="eyebrow">{title}</h3>
      {rows.length === 0 ? (
        <p className="muted small">None</p>
      ) : (
        <ul className="compare-list small">
          {rows.map((row, index) => (
            <li key={index}>
              <span className="mono">
                {row.a_label ?? "?"} · {row.b_label ?? "?"}
              </span>{" "}
              {Math.round(row.similarity * 100)}% alike
              {row.finding ? ` — ${row.finding} (${row.found_by === "rule" ? "Rule" : row.found_by === "person" ? "Person" : "AI"})` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Thresholds (US-06): sliders with a live preview of what a candidate value would compare and
 *  skip, saved without code changes and applied by re-analysis (no re-upload). */
export function ThresholdsTab({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  const queryClient = useQueryClient();
  const notify = useToast();
  const [similarity, setSimilarity] = useState<number | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [previewed, setPreviewed] = useState<[number, number] | null>(null);
  const sim = similarity ?? project.data?.similarity_threshold ?? 0.75;
  const conf = confidence ?? project.data?.confidence_threshold ?? 0.5;
  useEffect(() => {
    const timer = setTimeout(() => setPreviewed([sim, conf]), PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [sim, conf]);
  const preview = usePreview(projectId, previewed?.[0] ?? sim, previewed?.[1] ?? conf);

  const save = useMutation({
    mutationFn: () =>
      apiFetch(`/projects/${projectId}`, {
        method: "PATCH",
        json: { similarity_threshold: sim, confidence_threshold: conf },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      notify("Thresholds saved — re-analyse to apply them to existing requirements", "success");
    },
    onError: (error) => notify(error instanceof ApiError ? error.message : "Could not save", "error"),
  });
  const reanalyse = useMutation({
    mutationFn: () => apiFetch<{ queued: number }>(`/projects/${projectId}/reanalyse`, { method: "POST" }),
    onSuccess: (result) => notify(`Re-analysis queued for ${result.queued} item${result.queued === 1 ? "" : "s"}`, "success"),
    onError: (error) => notify(error instanceof ApiError ? error.message : "Could not re-analyse", "error"),
  });
  const data = preview.data;
  const changed =
    project.data && (sim !== project.data.similarity_threshold || conf !== project.data.confidence_threshold);

  return (
    <section aria-label="Thresholds" className="form-stack">
      <label>
        Similarity threshold: <strong>{sim.toFixed(2)}</strong>
        <input
          type="range"
          min={0.3}
          max={0.95}
          step={0.01}
          value={sim}
          onChange={(event) => setSimilarity(Number(event.target.value))}
        />
        <span className="muted small">Pairs at least this alike are sent to the AI. Rule checks ignore it.</span>
      </label>
      <label>
        Confidence threshold: <strong>{conf.toFixed(2)}</strong>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={conf}
          onChange={(event) => setConfidence(Number(event.target.value))}
        />
        <span className="muted small">Findings below it are marked “low confidence — review manually”.</span>
      </label>
      {data && (
        <div className="threshold-preview" aria-live="polite">
          <p>
            At {data.similarity.threshold.toFixed(2)}: <strong>{data.similarity.pairs_above}</strong> of{" "}
            {data.similarity.pairs_compared} pairs would be compared (now{" "}
            {data.similarity.current.toFixed(2)}).{" "}
            {data.similarity.truncated && <span className="muted small">Large project: the first 500 requirements.</span>}
          </p>
          <p>
            At {data.confidence.threshold.toFixed(2)}: {data.confidence.confident} AI findings confident,{" "}
            {data.confidence.low_confidence} low confidence.
          </p>
          <div className="preview-columns">
            <Examples title="Just above — compared" rows={data.similarity.above} />
            <Examples title="Just below — skipped" rows={data.similarity.below} />
          </div>
        </div>
      )}
      <div>
        <Button variant="primary" disabled={!changed} loading={save.isPending} onClick={() => save.mutate()}>
          Save thresholds
        </Button>{" "}
        <Button loading={reanalyse.isPending} onClick={() => reanalyse.mutate()}>
          Re-analyse the project
        </Button>
      </div>
    </section>
  );
}

/** Project settings (US-06, US-57): thresholds and decision rules. Managers only edit. */
export function ProjectSettings({ tab: initial = "thresholds" }: { tab?: "thresholds" | "decision-rules" }) {
  const { workspaceId = "", projectId = "" } = useParams();
  const { can } = usePermissions({ projectId });
  const [tab, setTab] = useState<string>(initial);
  const tabs = [
    ...(can("project.manage") ? [{ id: "thresholds", label: "Thresholds" }] : []),
    { id: "decision-rules", label: "Decision rules" },
  ];
  const selected = tabs.some((item) => item.id === tab) ? tab : "decision-rules";
  return (
    <div className="page">
      <header className="page-header">
        <h1>Project settings</h1>
      </header>
      <Tabs label="Project settings" tabs={tabs} selected={selected} onSelect={setTab}>
        {selected === "thresholds" && <ThresholdsTab projectId={projectId} />}
        {selected === "decision-rules" && <DecisionRulesTab workspaceId={workspaceId} projectId={projectId} />}
      </Tabs>
    </div>
  );
}
