import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import type { UUID } from "../../api/types";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { WordDiff } from "../../components/WordDiff";
import {
  lint,
  segments,
  useImproveWording,
  useLintCatalogue,
  usePreflight,
  type LikelyFinding,
  type LintResult,
} from "./authoring";

const LINT_DEBOUNCE_MS = 300; // NFR-34: lint within 300 ms of typing pausing
const QUALITY_WORDS = { good: "Good", fair: "Fair", poor: "Poor" } as const;

export interface AuthoringPanelProps {
  projectId: string;
  text: string;
  /** A change request's requirement (US-33): pre-flight does not compare it with itself. */
  requirementId?: UUID;
  /** The member accepted the AI wording: put it in the draft. */
  onUseWording: (proposed: string) => void;
}

/** Lint, pre-flight check and AI wording beside the composer (interface design §5.1–5.2).
 *  Nothing here blocks proposing; the AI parts are labelled and applied only on Accept. */
export function AuthoringPanel({ projectId, text, requirementId, onUseWording }: AuthoringPanelProps) {
  const catalogue = useLintCatalogue();
  const [linted, setLinted] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setLinted(text), LINT_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);
  const result = useMemo(
    () => (catalogue.data && linted.trim() ? lint(linted, catalogue.data) : null),
    [catalogue.data, linted],
  );

  return (
    <section className="authoring-panel" aria-label="Quality and checks">
      <Quality text={linted} result={result} />
      <Preflight projectId={projectId} text={text} requirementId={requirementId} />
      <Wording projectId={projectId} text={text} onUse={onUseWording} />
    </section>
  );
}

function Quality({ text, result }: { text: string; result: LintResult | null }) {
  if (!result) {
    return (
      <div>
        <div className="eyebrow">Quality</div>
        <p className="muted small">Start writing to see hints.</p>
      </div>
    );
  }
  const dots = Math.max(1, Math.round(result.score / 20));
  return (
    <div>
      <div className="eyebrow">Quality</div>
      <p className="quality-meter" aria-label={`Quality ${QUALITY_WORDS[result.quality]}, ${result.score} of 100`}>
        <span aria-hidden="true">{"●".repeat(dots) + "○".repeat(5 - dots)}</span>{" "}
        <strong>{QUALITY_WORDS[result.quality]}</strong>
      </p>
      {result.issues.length > 0 && (
        <>
          <p className="lint-text">
            {segments(text, result.issues).map((part, index) =>
              part.issue ? (
                <mark key={index} className={`lint-${part.issue.severity}`} title={part.issue.message}>
                  {part.text}
                </mark>
              ) : (
                <span key={index}>{part.text}</span>
              ),
            )}
          </p>
          <ul className="lint-list">
            {result.issues.map((issue) => (
              <li key={`${issue.ruleId}-${issue.start}`}>
                <span className={`lint-severity lint-${issue.severity}`}>
                  {issue.severity === "error" ? "✕" : issue.severity === "warning" ? "⚠" : "i"} {issue.severity}
                </span>{" "}
                “{issue.match}” — {issue.message} <span className="muted small">{issue.hint}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {result.issues.length === 0 && <p className="small">✓ No lint hints.</p>}
      <p className="muted small">Hints never block proposing.</p>
    </div>
  );
}

function Preflight({ projectId, text, requirementId }: { projectId: string; text: string; requirementId?: UUID }) {
  const preflight = usePreflight(projectId);
  const data = preflight.data;
  const error = preflight.error instanceof ApiError ? preflight.error : null;
  return (
    <div>
      <div className="eyebrow">Pre-flight check</div>
      <Button
        variant="secondary"
        disabled={!text.trim() || preflight.isPending}
        onClick={() => preflight.mutate({ text, requirementId })}
      >
        {preflight.isPending ? "Checking…" : "Run check"}
      </Button>{" "}
      <span className="muted small">Dry run: nothing is saved. Uses up to 4 AI calls.</span>
      {error && <p role="alert">{error.message}</p>}
      {data && (
        <div aria-live="polite">
          <p className="small">
            <Badge tone="ai">AI</Badge>{" "}
            {data.budget.remaining === null
              ? "No monthly limit on this project."
              : `${data.budget.remaining} of ${data.budget.monthly} analyses left this month.`}
          </p>
          {data.status === "unavailable" && <p className="muted small">No AI model is configured: only the lint ran.</p>}
          {data.status === "budget" && <p role="alert">This month&rsquo;s AI budget is used up.</p>}
          {data.status === "partial" && <p className="muted small">Some comparisons could not be completed.</p>}
          {data.status !== "unavailable" && data.likely_findings.length === 0 && (
            <p className="small">
              No likely issues found by the check — analysis can miss conflicts.
            </p>
          )}
          {data.likely_findings.length > 0 && (
            <>
              <ul className="likely-list">
                {data.likely_findings.map((found, index) => (
                  <li key={index}>
                    <strong>{found.category === "Conflicting" ? "✕" : "!"} Likely {found.category.toLowerCase()}</strong>
                    {found.label ? ` with ${found.label}` : " in the wording"} ·{" "}
                    {Math.round(found.confidence * 100)}%{found.low_confidence ? " (low confidence)" : ""}
                    <br />
                    <span className="muted small">{found.rationale}</span>
                  </li>
                ))}
              </ul>
              <GhostMap findings={data.likely_findings} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** The draft as a dashed ghost node with an edge to each requirement it may clash with. */
export function GhostMap({ findings }: { findings: LikelyFinding[] }) {
  const linked = findings.filter((f) => f.label);
  const width = 240;
  const height = 120;
  const xs = linked.map((_, index) =>
    linked.length === 1 ? width / 2 : 30 + (index * (width - 60)) / (linked.length - 1),
  );
  return (
    <svg
      className="ghost-map"
      role="img"
      aria-label={`Mini-map: the draft and ${linked.length} requirement${linked.length === 1 ? "" : "s"} it may affect`}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
    >
      {linked.map((found, index) => (
        <g key={index}>
          <line
            x1={width / 2}
            y1={30}
            x2={xs[index]}
            y2={95}
            className={found.category === "Conflicting" ? "ghost-edge-conflict" : "ghost-edge"}
          />
          <circle cx={xs[index]} cy={95} r={10} className="ghost-target" />
          <text x={xs[index]} y={118} textAnchor="middle" className="ghost-label">
            {found.label}
          </text>
        </g>
      ))}
      <circle cx={width / 2} cy={30} r={14} className="ghost-node" />
      <text x={width / 2} y={12} textAnchor="middle" className="ghost-label">
        Draft
      </text>
    </svg>
  );
}

function Wording({ projectId, text, onUse }: { projectId: string; text: string; onUse: (proposed: string) => void }) {
  const improve = useImproveWording(projectId);
  const [dismissed, setDismissed] = useState(false);
  const data = dismissed ? null : improve.data;
  const error = improve.error instanceof ApiError ? improve.error : null;
  return (
    <div>
      <div className="eyebrow">Improve wording</div>
      <Button
        variant="secondary"
        disabled={!text.trim() || improve.isPending}
        onClick={() => {
          setDismissed(false);
          improve.mutate(text);
        }}
      >
        {improve.isPending ? "Asking the AI…" : "✨ Improve wording (AI)"}
      </Button>
      {error && <p role="alert">{error.message}</p>}
      {data && (
        <div className="wording-suggestion">
          <p className="small">
            <Badge tone="ai">AI</Badge> suggestion · quality {data.lint_before} → {data.lint_after}
          </p>
          <WordDiff before={data.original} after={data.proposed} label="Suggested wording, as a diff" />
          {data.tbd_slots.length > 0 && (
            <p className="small">Fill in before proposing: {data.tbd_slots.join(", ")}.</p>
          )}
          {data.changes.length > 0 && (
            <ul className="muted small">
              {data.changes.map((change) => (
                <li key={change}>{change}</li>
              ))}
            </ul>
          )}
          <Button
            onClick={() => {
              onUse(data.proposed);
              setDismissed(true);
            }}
          >
            Accept
          </Button>{" "}
          <Button variant="ghost" onClick={() => setDismissed(true)}>
            Dismiss
          </Button>
        </div>
      )}
    </div>
  );
}
