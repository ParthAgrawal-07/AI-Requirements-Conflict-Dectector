// A word diff of two texts (Pranshu — US-12 version history; reused by the change request pages,
// US-33). Words are compared by longest common subsequence; whitespace stays with the word before
// it, so the rendered text reads exactly like either version. It is a *word* diff on purpose:
// spacing is not compared (proposals are trimmed server-side and the paragraph collapses it).

import { useMemo } from "react";

export type DiffKind = "same" | "added" | "removed";

export interface DiffPart {
  kind: DiffKind;
  text: string;
}

function tokens(text: string): string[] {
  return text.match(/\S+\s*/g) ?? [];
}

/** ``before`` → ``after`` as same / removed / added runs (adjacent runs of a kind are merged). */
export function wordDiff(before: string, after: string): DiffPart[] {
  const a = tokens(before);
  const b = tokens(after);
  // The words themselves, trimmed once rather than on every comparison of the LCS.
  const wa = a.map((token) => token.trim());
  const wb = b.map((token) => token.trim());
  const lengths = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lengths[i][j] = wa[i] === wb[j] ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const parts: DiffPart[] = [];
  const push = (kind: DiffKind, text: string) => {
    const last = parts[parts.length - 1];
    if (last && last.kind === kind) last.text += text;
    else parts.push({ kind, text });
  };
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (wa[i] === wb[j]) {
      push("same", b[j]);
      i++;
      j++;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      push("removed", a[i++]);
    } else {
      push("added", b[j++]);
    }
  }
  while (i < a.length) push("removed", a[i++]);
  while (j < b.length) push("added", b[j++]);
  return parts;
}

export interface WordDiffProps {
  before: string;
  after: string;
  label?: string;
}

/** Removed words struck through, added words underlined — and said in words for screen readers.
 *  The label names a group: ARIA does not allow naming a paragraph. Recomputed only when a text
 *  changes, not on every render of the form around it. */
export function WordDiff({ before, after, label = "Changes" }: WordDiffProps) {
  const parts = useMemo(() => wordDiff(before, after), [before, after]);
  return (
    <div role="group" aria-label={label}>
      <p className="word-diff">
        {parts.map((part, index) =>
          part.kind === "same" ? (
            <span key={index}>{part.text}</span>
          ) : part.kind === "removed" ? (
            <del key={index}>
              <span className="sr-only">removed: </span>
              {part.text}
            </del>
          ) : (
            <ins key={index}>
              <span className="sr-only">added: </span>
              {part.text}
            </ins>
          ),
        )}
      </p>
    </div>
  );
}
