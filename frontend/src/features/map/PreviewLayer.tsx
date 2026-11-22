import { useChangeRequests } from "../changes/api";
import { type DraftPreview, type GraphPreview, useGraphPreview } from "./history";

export interface Layers {
  baseline: boolean;
  proposed: boolean;
  preview: boolean;
}

export interface PreviewLayerProps {
  projectId: string;
  layers: Layers;
  onLayers: (layers: Layers) => void;
  changeRequestId: string | null;
  onChangeRequest: (id: string | null) => void;
  draft: DraftPreview | null;
  onClearDraft: () => void;
  /** The past is read-only: no preview over a frozen map. */
  readOnly: boolean;
}

const LAYER_TEXT: { key: keyof Layers; label: string; hint: string }[] = [
  { key: "baseline", label: "Baseline", hint: "Approved and implemented (solid)" },
  { key: "proposed", label: "Proposed", hint: "Proposed and under review (dashed)" },
  { key: "preview", label: "Preview", hint: "What a change or a draft would do (ghost)" },
];

/** The map's layers (Pranshu — US-50, FR-85, SX-17): Baseline, Proposed — on by default — and
 *  Preview, which shows an open change request (edges it would resolve fade, new findings glow)
 *  or the pre-flight draft handed over from the composer. */
export function PreviewLayer({
  projectId,
  layers,
  onLayers,
  changeRequestId,
  onChangeRequest,
  draft,
  onClearDraft,
  readOnly,
}: PreviewLayerProps) {
  const open = useChangeRequests(projectId, { status: "open", limit: 50, offset: 0 });
  const preview = useGraphPreview(layers.preview && !readOnly ? changeRequestId : null);
  return (
    <div className="preview-layer">
      <fieldset className="pill-group">
        <legend className="small">Layers</legend>
        {LAYER_TEXT.map((layer) => (
          <button
            key={layer.key}
            type="button"
            className="pill"
            title={layer.hint}
            aria-pressed={layers[layer.key]}
            disabled={layer.key === "preview" && readOnly}
            onClick={() => onLayers({ ...layers, [layer.key]: !layers[layer.key] })}
          >
            {layer.label}
          </button>
        ))}
      </fieldset>
      {layers.preview && !readOnly && (
        <div className="preview-source">
          <label className="small">
            Preview{" "}
            <select
              className="select"
              value={changeRequestId ?? (draft ? "draft" : "")}
              onChange={(e) => {
                const value = e.target.value;
                if (value !== "draft") onChangeRequest(value || null);
              }}
            >
              <option value="">Choose an open change request…</option>
              {draft && <option value="draft">The pre-flight draft</option>}
              {(open.data?.items ?? []).map((cr) => (
                <option key={cr.id} value={cr.id}>
                  {cr.key} on {cr.requirement.label ?? "a requirement"}
                </option>
              ))}
            </select>
          </label>
          {draft && !changeRequestId && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClearDraft}>
              Clear the draft
            </button>
          )}
          <PreviewSentences preview={preview.data} draft={changeRequestId ? null : draft} />
        </div>
      )}
    </div>
  );
}

function PreviewSentences({ preview, draft }: { preview?: GraphPreview; draft: DraftPreview | null }) {
  if (preview) {
    return (
      <div aria-live="polite" className="small">
        {preview.sentences.map((sentence) => (
          <p key={sentence}>{sentence}</p>
        ))}
        {preview.checks_pending && <p className="muted">The ghost edges appear when the checks finish.</p>}
      </div>
    );
  }
  if (draft) {
    const count = draft.findings.filter((f) => f.requirement_id).length;
    return (
      <p aria-live="polite" className="small">
        <span className="badge badge-ai">
          <span className="badge-icon" aria-hidden="true">
            AI
          </span>
          Pre-flight
        </span>{" "}
        The draft would relate to {count} requirement{count === 1 ? "" : "s"} (likely, not checked).
      </p>
    );
  }
  return null;
}
