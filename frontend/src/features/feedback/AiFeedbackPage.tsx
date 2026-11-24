import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { acceptanceRate, OUTCOME_TEXT, useAiFeedback, useSetFeedbackThreshold, type FeedbackPattern } from "./api";

function rate(pattern: FeedbackPattern): string {
  return pattern.false_positive_rate === null ? "—" : `${Math.round(pattern.false_positive_rate * 100)}%`;
}

/** Insights › AI feedback (Abhijeet — US-15, US-45, FR-18, NFR-22; interface design §12): why
 *  people dismissed findings, per category and per pattern (a rule, the AI, a person), the patterns
 *  dismissed often enough to look at, and what happened to AI suggestions. A signal for people:
 *  nothing retrains itself from it. */
export function AiFeedbackPage() {
  const { workspaceId = "", projectId = "" } = useParams();
  const report = useAiFeedback(projectId);
  const data = report.data;
  const accepted = data ? acceptanceRate(data.suggestion_totals) : null;
  const base = `/w/${workspaceId}/p/${projectId}`;
  return (
    <div className="page ai-feedback">
      <p>
        <Link to={`${base}/insights`}>← Insights</Link>
      </p>
      <header className="page-header">
        <div>
          <h1>AI feedback</h1>
          <p className="muted small">
            What reviewers told the tool it got wrong. This is for people tuning prompts and rules — the tool does
            not learn from it by itself.
          </p>
        </div>
      </header>
      {report.isLoading && <p className="muted">Loading…</p>}
      {report.isError && <p role="alert">The feedback report could not be loaded.</p>}
      {data && (
        <>
          <Threshold projectId={projectId} threshold={data.threshold} />
          <section aria-labelledby="fb-surfaced">
            <h2 id="fb-surfaced">Patterns to look at ({data.surfaced.length})</h2>
            {data.surfaced.length === 0 ? (
              <p className="muted">No pattern has been dismissed {data.threshold} times or more.</p>
            ) : (
              <ul className="surfaced-list">
                {data.surfaced.map(({ category, pattern }) => (
                  <li key={`${category}-${pattern.pattern}`}>
                    <strong>{category}</strong> · <span className="mono">{pattern.pattern}</span> — dismissed{" "}
                    {pattern.dismissed} times ({rate(pattern)} of decided)
                    {pattern.reasons[0] && <span className="muted"> · most often: “{pattern.reasons[0].reason}”</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section aria-labelledby="fb-categories">
            <h2 id="fb-categories">Dismissed findings by category</h2>
            {data.categories.length === 0 && <p className="muted">No finding has been reviewed yet.</p>}
            {data.categories.map((category) => (
              <details key={category.category} className="feedback-category" open={category.dismissed > 0}>
                <summary>
                  <strong>{category.category}</strong>{" "}
                  <span className="muted small">
                    {category.dismissed} dismissed · {category.confirmed} accepted · {category.open} open
                  </span>
                </summary>
                {category.patterns.length > 0 && (
                  <table className="table">
                    <caption className="sr-only">{category.category} findings by pattern</caption>
                    <thead>
                      <tr>
                        <th scope="col">Found by</th>
                        <th scope="col">Accepted</th>
                        <th scope="col">Dismissed</th>
                        <th scope="col">Dismissed share</th>
                        <th scope="col">Reasons</th>
                      </tr>
                    </thead>
                    <tbody>
                      {category.patterns.map((pattern) => (
                        <tr key={pattern.pattern}>
                          <td>
                            {pattern.source === "ai" ? <Badge tone="ai">AI</Badge> : <span className="mono">{pattern.pattern}</span>}
                            {pattern.surfaced && <span className="small"> ⚠ look at this</span>}
                          </td>
                          <td>{pattern.confirmed}</td>
                          <td>{pattern.dismissed}</td>
                          <td>{rate(pattern)}</td>
                          <td>
                            {pattern.reasons.length === 0 ? (
                              <span className="muted">—</span>
                            ) : (
                              <ul className="reason-list">
                                {pattern.reasons.map((r) => (
                                  <li key={r.reason}>
                                    {r.reason} <span className="muted">×{r.count}</span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </details>
            ))}
          </section>
          <section aria-labelledby="fb-suggestions">
            <h2 id="fb-suggestions">AI suggestions</h2>
            <p className="small">
              Acceptance rate:{" "}
              <strong>{accepted === null ? "—" : `${accepted}%`}</strong>{" "}
              <span className="muted">(accepted, with or without edits, of those decided)</span>
            </p>
            <table className="table">
              <caption className="sr-only">Suggestion outcomes by category</caption>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  {OUTCOME_TEXT.map(([key, text]) => (
                    <th key={key} scope="col">
                      {text}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.categories
                  .filter((c) => Object.values(c.suggestions).some((n) => n > 0))
                  .map((c) => (
                    <tr key={c.category}>
                      <th scope="row">{c.category}</th>
                      {OUTCOME_TEXT.map(([key]) => (
                        <td key={key}>{c.suggestions[key] ?? 0}</td>
                      ))}
                    </tr>
                  ))}
                <tr>
                  <th scope="row">All</th>
                  {OUTCOME_TEXT.map(([key]) => (
                    <td key={key}>
                      <strong>{data.suggestion_totals[key] ?? 0}</strong>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

function Threshold({ projectId, threshold }: { projectId: string; threshold: number }) {
  const { can } = usePermissions({ projectId });
  const notify = useToast();
  const update = useSetFeedbackThreshold(projectId);
  const [value, setValue] = useState(String(threshold));
  if (!can("project.manage")) {
    return <p className="muted small">A pattern is listed once it has been dismissed {threshold} times.</p>;
  }
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = Number(value);
    if (!Number.isInteger(next) || next < 1 || next > 100) return;
    update.mutate(next, {
      onSuccess: () => notify(`Patterns are listed after ${next} dismissals`, "success"),
      onError: (error) => notify(error instanceof ApiError ? error.message : "Could not save it", "error"),
    });
  };
  return (
    <form className="inline-form" onSubmit={submit} aria-label="Dismissal threshold">
      <label>
        List a pattern after{" "}
        <input className="input" type="number" min={1} max={100} value={value} onChange={(e) => setValue(e.target.value)} />{" "}
        dismissals
      </label>
      <Button type="submit" size="sm" loading={update.isPending}>
        Save
      </Button>
    </form>
  );
}
