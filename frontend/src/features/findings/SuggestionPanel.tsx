import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { WordDiff } from "../../components/WordDiff";
import { useFinding } from "./api";
import {
  REJECTIONS,
  TBD,
  useRegenerate,
  useSuggestion,
  useSuggestionFeedback,
  type FeedbackAction,
  type Prefill,
} from "./suggestions";

const LETTERS = ["A", "B", "C"];

/** The text with every ``[TBD — confirm]`` highlighted: a value a person must supply. */
function WithPlaceholders({ text }: { text: string }) {
  const parts = text.split(TBD);
  return (
    <>
      {parts.map((part, index) => (
        <span key={index}>
          {part}
          {index < parts.length - 1 && <mark className="tbd">{TBD}</mark>}
        </span>
      ))}
    </>
  );
}

/** 💡 Suggested solutions (US-45, interface design §8a): up to three AI options with their
 *  trade-off and confidence; people accept, edit, reject with a reason, defer, mark a preference
 *  or regenerate. Accepting opens a pre-filled change — it never changes a requirement itself. */
export function SuggestionPanel({ findingId }: { findingId: string }) {
  const { workspaceId = "", projectId = "" } = useParams();
  const navigate = useNavigate();
  const notify = useToast();
  const { can } = usePermissions({ projectId });
  const suggestion = useSuggestion(findingId);
  const finding = useFinding(findingId);
  const feedback = useSuggestionFeedback(findingId);
  const regenerate = useRegenerate(findingId);
  const [selected, setSelected] = useState(0);
  const [editing, setEditing] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const base = `/w/${workspaceId}/p/${projectId}`;
  const data = suggestion.data;

  if (!data) return suggestion.isLoading ? <p className="muted small">Loading suggestions…</p> : null;
  if (data.status === "pending" || data.status === "waiting_budget") {
    return (
      <section className="suggestion-panel" aria-label="Suggested solutions">
        <h3>💡 Suggested solutions <Badge tone="ai">AI</Badge></h3>
        <p className="muted small" aria-live="polite">
          {data.status === "pending" ? "Generating suggestions…" : "Waiting for this month's AI budget."}
        </p>
      </section>
    );
  }
  if (data.status === "failed") {
    return (
      <section className="suggestion-panel" aria-label="Suggested solutions">
        <h3>💡 Suggested solutions <Badge tone="ai">AI</Badge></h3>
        <p className="muted small">The AI could not suggest a resolution that keeps to the rules.</p>
      </section>
    );
  }

  const option = data.options[selected];
  const current = finding.data?.requirements.find((r) => r.id === option?.target_requirement_id)?.body;
  const mayRespond = can("req.comment");
  const mayAccept = can("rcr.open") || can("req.propose");

  const open = (prefill: Prefill) => {
    if (prefill.kind === "post") {
      navigate(`${base}/requirements/new`, { state: { prefill } });
    } else {
      const resolves = prefill.issue_number ? `&resolves=${prefill.issue_number}` : "";
      navigate(`${base}/changes/new?requirement=${prefill.requirement_id}${resolves}`, { state: { prefill } });
    }
  };

  const respond = (action: FeedbackAction, extra: { final_text?: string } = {}) =>
    feedback.mutate(
      {
        suggestionId: data.id,
        action,
        option_index: action === "deferred" ? undefined : selected,
        ...extra,
      },
      {
        onSuccess: (result) => {
          if (result.prefill) open(result.prefill);
          else notify(action === "prefer" ? `Option ${LETTERS[selected]} marked as your preference` : "Recorded", "success");
        },
        onError: (error) => notify(error instanceof ApiError ? error.message : "Could not record it", "error"),
      },
    );

  return (
    <section className="suggestion-panel" aria-label="Suggested solutions">
      <h3>
        💡 Suggested solutions <Badge tone="ai">AI</Badge>{" "}
        <span className="muted small">{data.category}</span>
      </h3>
      {data.instruction && <p className="muted small">Regenerated with: “{data.instruction}”</p>}
      <fieldset className="suggestion-options">
        <legend className="sr-only">Options</legend>
        {data.options.map((item, index) => {
          const backers = data.preferences.filter((p) => p.option_index === index);
          return (
            <label key={index} className="suggestion-option">
              <input type="radio" name={`option-${data.id}`} checked={selected === index} onChange={() => {
                setSelected(index);
                setEditing(null);
              }} />{" "}
              <strong>{LETTERS[index]}</strong> <WithPlaceholders text={item.text} />{" "}
              <span className="muted small">
                {item.target ? `replaces ${item.target}` : "records a link"} · {Math.round(item.confidence * 100)}%
              </span>
              <br />
              <span className="small">Trade-off: {item.trade_off}</span>
              {backers.length > 0 && (
                <span className="small preference-marks">
                  {" "}
                  {backers.map((p) => `${p.full_name} ✓`).join(" · ")}
                </span>
              )}
            </label>
          );
        })}
      </fieldset>

      {option && current && editing === null && (
        <WordDiff before={current} after={option.text} label={`Diff for option ${LETTERS[selected]}`} />
      )}
      {option && option.tbd_slots.length > 0 && (
        <p className="small">To fill in before a change can open: {option.tbd_slots.join(", ")}.</p>
      )}

      {editing !== null && (
        <label className="form-stack">
          Your wording
          <textarea rows={3} value={editing} onChange={(event) => setEditing(event.target.value)} />
        </label>
      )}

      {mayRespond && option && (
        <div className="suggestion-actions">
          {mayAccept && option.target_requirement_id && editing === null && (
            <>
              <Button variant="primary" onClick={() => respond("accepted")} loading={feedback.isPending}>
                Accept {LETTERS[selected]} → open change
              </Button>{" "}
              <Button onClick={() => setEditing(option.text)}>Edit {LETTERS[selected]} first</Button>{" "}
            </>
          )}
          {editing !== null && (
            <>
              <Button
                variant="primary"
                disabled={!editing.trim()}
                onClick={() => respond("accepted_edited", { final_text: editing })}
              >
                Accept edited text → open change
              </Button>{" "}
              <Button variant="ghost" onClick={() => setEditing(null)}>
                Cancel
              </Button>{" "}
            </>
          )}
          <Button onClick={() => respond("prefer")}>Mark {LETTERS[selected]} as my preference</Button>{" "}
          <Button variant="ghost" onClick={() => respond("deferred")}>
            Defer — not decided yet
          </Button>
          <p className="small reject-reasons">
            Reject {LETTERS[selected]} because:{" "}
            {REJECTIONS.map((reason, index) => (
              <span key={reason.action}>
                {index > 0 && " · "}
                <button type="button" className="link-button" onClick={() => respond(reason.action)}>
                  {reason.label}
                </button>
              </span>
            ))}
          </p>
          <form
            className="inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (instruction.trim().length >= 3) regenerate.mutate(instruction.trim());
            }}
          >
            <label>
              ↻ Regenerate with instruction{" "}
              <input value={instruction} onChange={(event) => setInstruction(event.target.value)}
                     placeholder="keep 30 minutes for the web app" maxLength={500} />
            </label>
            <Button type="submit" loading={regenerate.isPending}>
              Regenerate
            </Button>
          </form>
        </div>
      )}
      {data.my_outcome && <p className="muted small">Your response: {data.my_outcome.replace(/_/g, " ")}.</p>}
      <p className="muted small">Suggestions are proposals. Accepting one does not mean it is correct.</p>
    </section>
  );
}
