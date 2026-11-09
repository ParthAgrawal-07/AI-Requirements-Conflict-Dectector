import { useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import type { Member } from "./api";
import { activeQuery, encode, type Picked } from "./mentions";

export interface ComposerProps {
  label: string; // "Message #general" / "Reply in thread"
  members: Member[];
  onSend: (body: string) => Promise<unknown>;
  initial?: string;
  initialPicked?: Picked[]; // mentions already in `initial` (editing)
  submitLabel?: string;
  onCancel?: () => void;
}

const MAX_SUGGESTIONS = 6;

/** The message box (US-29): Enter sends, Shift+Enter adds a line, "@" opens the member picker
 *  (arrow keys, Enter or Tab to pick, Escape to close). Works with the keyboard alone. */
export function Composer({
  label,
  members,
  onSend,
  initial = "",
  initialPicked = [],
  submitLabel = "Send",
  onCancel,
}: ComposerProps) {
  const [text, setText] = useState(initial);
  const [picked, setPicked] = useState<Picked[]>(initialPicked);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const listId = useId();

  const query = dismissed ? null : activeQuery(text, caret);
  const suggestions = query
    ? members
        .filter((m) => m.user.full_name.toLowerCase().includes(query.query.toLowerCase()))
        .slice(0, MAX_SUGGESTIONS)
    : [];
  const open = suggestions.length > 0;

  function pick(member: Member) {
    if (!query) return;
    const name = member.user.full_name;
    const next = `${text.slice(0, query.start)}@${name} ${text.slice(caret)}`;
    const position = query.start + name.length + 2;
    setText(next);
    setPicked((current) =>
      current.some((p) => p.userId === member.user.id) ? current : [...current, { userId: member.user.id, name }],
    );
    setActive(0);
    requestAnimationFrame(() => {
      box.current?.setSelectionRange(position, position);
      setCaret(position);
    });
  }

  async function send() {
    const body = encode(text.trim(), picked.filter((p) => text.includes(`@${p.name}`)));
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      await onSend(body);
      setText("");
      setPicked([]);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "The message could not be sent.");
    } finally {
      setSending(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (open) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActive((index) => (index + step + suggestions.length) % suggestions.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        pick(suggestions[Math.min(active, suggestions.length - 1)]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setDismissed(true);
        return;
      }
    }
    if (event.key === "Escape" && onCancel) {
      event.preventDefault();
      onCancel();
    } else if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <div className="composer">
      <textarea
        ref={box}
        aria-label={label}
        placeholder={`${label} — @ to mention, Enter to send`}
        value={text}
        rows={2}
        maxLength={4000}
        role="combobox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-autocomplete="list"
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        onChange={(event) => {
          setText(event.target.value);
          setCaret(event.target.selectionStart);
          setDismissed(false);
        }}
        onSelect={(event) => setCaret(event.currentTarget.selectionStart)}
        onKeyDown={onKeyDown}
      />
      {open && (
        <ul id={listId} role="listbox" aria-label="Mention a member" className="mention-list">
          {suggestions.map((member, index) => (
            <li
              key={member.user.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              className={index === active ? "mention-option active" : "mention-option"}
              onMouseDown={(event) => {
                event.preventDefault();
                pick(member);
              }}
            >
              {member.user.full_name} <span className="muted">· {member.role.name}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="composer-actions">
        {error && (
          <span role="alert" className="error-text">
            {error}
          </span>
        )}
        {onCancel && (
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button variant="primary" size="sm" loading={sending} onClick={() => void send()} disabled={!text.trim()}>
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}
