import { type RefObject, useRef, useState } from "react";
import { WordDiff } from "../../components/WordDiff";
import type { ChangeRequest, InlineComment, Review } from "./api";

export interface Quote {
  start_offset: number;
  end_offset: number;
  text: string;
}

export interface DiffViewProps {
  change: Pick<ChangeRequest, "kind" | "base_version" | "base_body" | "current_body" | "proposed_body" | "requirement">;
  reviews?: Review[];
  /** Given when the viewer may review: selecting words of the proposal offers an inline comment. */
  onQuote?: (quote: Quote) => void;
}

/** Where the selection sits inside ``container``'s text, or null when it is empty or outside. */
function selectedRange(container: HTMLElement): Quote | null {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null;
  const before = document.createRange();
  before.selectNodeContents(container);
  before.setEnd(range.startContainer, range.startOffset);
  const start = before.toString().length;
  const text = range.toString();
  return text.trim() ? { start_offset: start, end_offset: start + text.length, text } : null;
}

/** Select words with the mouse and press the button; or, from the keyboard (no selection), press it
 *  and type the words to quote — their first occurrence in the proposal is quoted. */
function QuotePicker({
  proposed,
  container,
  onQuote,
}: {
  proposed: string;
  container: RefObject<HTMLParagraphElement | null>;
  onQuote: (quote: Quote) => void;
}) {
  const [typing, setTyping] = useState(false);
  const [words, setWords] = useState("");
  const [missing, setMissing] = useState(false);

  if (typing) {
    return (
      <form
        className="row-actions"
        aria-label="Quote words"
        onSubmit={(event) => {
          event.preventDefault();
          const text = words.trim();
          const start = text ? proposed.indexOf(text) : -1;
          if (start < 0) {
            setMissing(true);
            return;
          }
          onQuote({ start_offset: start, end_offset: start + text.length, text });
          setTyping(false);
          setWords("");
          setMissing(false);
        }}
      >
        <label>
          Words to quote
          <input className="input" autoFocus value={words} onChange={(e) => setWords(e.target.value)} />
        </label>
        <button type="submit" className="link-button small">
          Quote
        </button>
        {missing && (
          <span className="field-error small" role="alert">
            Those words are not in the proposed text.
          </span>
        )}
      </form>
    );
  }
  return (
    <button
      type="button"
      className="link-button small"
      onMouseDown={(event) => event.preventDefault()} // keep the selection while clicking
      onClick={() => {
        const quote = container.current && selectedRange(container.current);
        if (quote) onQuote(quote);
        else setTyping(true); // keyboard users have no selection to give
      }}
    >
      Comment on the selected words
    </button>
  );
}

function quoted(body: string, comment: InlineComment): string | null {
  if (comment.start_offset === null || comment.end_offset === null) return null;
  return body.slice(comment.start_offset, comment.end_offset) || null;
}

/** The Files-changed tab (interface design §7.2): a word diff of the statement. When another
 *  request merged after this one was written ("needs update"), a three-way view — what changed
 *  underneath it, then what this request would change on top of the current text. */
export function DiffView({ change, reviews = [], onQuote }: DiffViewProps) {
  const proposalRef = useRef<HTMLParagraphElement>(null);
  const label = change.requirement.label ?? "The requirement";
  // By version, not text: a later version can restore the same words and still be a new base.
  const moved = change.base_version !== change.requirement.current_version;
  // Offsets of a dismissed review point into an earlier proposal text: no quote for those.
  const comments = reviews.flatMap((review) =>
    review.comments.map((comment) => ({
      comment,
      review,
      quote: review.dismissed || change.proposed_body === null ? null : quoted(change.proposed_body, comment),
    })),
  );

  if (change.kind === "deprecate" || change.proposed_body === null) {
    return (
      <section className="diff-view" aria-label="Files changed">
        <p>
          <strong>Deprecate {label}</strong> — it leaves the baseline. Its text stays in the version history.
        </p>
        <WordDiff before={change.current_body} after="" label="Text removed" />
      </section>
    );
  }

  const proposed = change.proposed_body;
  return (
    <section className="diff-view" aria-label="Files changed">
      {moved && (
        <div className="diff-block">
          <h3 className="eyebrow">
            Changed underneath: v{change.base_version} → v{change.requirement.current_version}
          </h3>
          <WordDiff before={change.base_body} after={change.current_body} label="Merged since this request was written" />
          {change.base_body === change.current_body && (
            <p className="muted small">The statement reads the same; the version still moved.</p>
          )}
        </div>
      )}
      <div className="diff-block">
        <h3 className="eyebrow">
          {moved ? `Current v${change.requirement.current_version} → proposed` : `v${change.base_version} → proposed`}
        </h3>
        <WordDiff before={moved ? change.current_body : change.base_body} after={proposed} label="Proposed changes" />
      </div>
      <div className="diff-block">
        <h3 className="eyebrow">Proposed text</h3>
        <p ref={proposalRef} className="requirement-quote proposal-text">
          {proposed}
        </p>
        {onQuote && <QuotePicker proposed={proposed} container={proposalRef} onQuote={onQuote} />}
      </div>
      {comments.length > 0 && (
        <div className="diff-block">
          <h3 className="eyebrow">Inline comments</h3>
          <ul className="comment-list">
            {comments.map(({ comment, review, quote }, index) => (
              <li key={`${review.id}-${index}`} className={review.dismissed ? "comment dismissed" : "comment"}>
                <p className="muted small">
                  <strong>{review.reviewer?.full_name ?? "A former member"}</strong> · revision {review.proposal_revision}
                  {review.dismissed && " · earlier revision"}
                </p>
                {quote && <q className="mono small">{quote}</q>}
                <p>{comment.body}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
