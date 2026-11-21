import type { ReactNode } from "react";
import type { SimilarRequirement } from "./api";

export interface PreviewPaneProps {
  statement: string | null;
  missing: string[];
  similar: SimilarRequirement[];
  similarLoading: boolean;
  /** Lint, pre-flight and AI wording (US-51), below the hints. */
  children?: ReactNode;
}

/** The live sentence and, beside it, the most similar existing requirements (interface design
 *  §5.1). A hint is a pointer to look at, never a finding: similarity is not a conflict (DR-10). */
export function PreviewPane({
  statement,
  missing,
  similar,
  similarLoading,
  children,
}: PreviewPaneProps) {
  return (
    <aside className="preview-pane" aria-label="Preview and similar requirements">
      <div className="eyebrow">Preview</div>
      <p className="preview-sentence" aria-live="polite">
        {statement ? (
          <q>{statement}</q>
        ) : (
          <span className="muted">Fill in: {missing.join(", ")}</span>
        )}
      </p>

      <div className="eyebrow">Similar requirements</div>
      {similarLoading && <p className="muted small">Looking…</p>}
      {!similarLoading && similar.length === 0 && (
        <p className="muted small">None that look alike yet.</p>
      )}
      {similar.length > 0 && (
        <ul className="similar-list">
          {similar.map((hint) => (
            <li key={hint.requirement_id}>
              <span className="mono">{hint.label ?? "Unnumbered"}</span>{" "}
              <span className="muted small">{hint.state.replace("_", " ")}</span>
              <br />
              {hint.preview}{" "}
              <span className="muted small" title="Similarity of the wording, not a verdict">
                {Math.round(hint.similarity * 100)}% alike
              </span>
            </li>
          ))}
        </ul>
      )}
      {children}
    </aside>
  );
}
