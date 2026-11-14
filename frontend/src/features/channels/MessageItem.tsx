import { useState } from "react";
import { useAuth } from "../../app/auth";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useDeleteMessage, useEditMessage, type Member, type Message } from "./api";
import { Composer } from "./Composer";
import { segments } from "./mentions";

export interface MessageItemProps {
  message: Message;
  members: Member[];
  canPost: boolean;
  onOpenThread?: (message: Message) => void;
}

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** The body as text segments; mentions shown as "@Name". Never HTML. */
export function MessageBody({ message, names }: { message: Message; names: Map<string, string> }) {
  if (message.deleted) return <p className="message-body muted">This message was deleted.</p>;
  return (
    <p className="message-body">
      {segments(message.body, names).map((part, index) =>
        part.kind === "text" ? (
          <span key={index}>{part.text}</span>
        ) : (
          <span key={index} className="mention">
            @{part.name}
          </span>
        ),
      )}
    </p>
  );
}

/** One message (US-29): author (or "former member", US-26), time, "edited", the body, the thread
 *  link, and Edit / Delete on your own chat messages. Requirement posts are cards, never edited. */
export function MessageItem({ message, members, canPost, onOpenThread }: MessageItemProps) {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const edit = useEditMessage();
  const remove = useDeleteMessage();
  const names = new Map(members.map((m) => [m.user.id, m.user.full_name]));
  const author = message.author;
  const mine = author !== null && user?.id === author.id;
  const editable = mine && canPost && message.kind === "chat" && !message.deleted;

  return (
    <article
      className={`message message-${message.kind}`}
      aria-label={author ? `Message from ${author.full_name}` : "Message from the app"}
    >
      <header className="message-header">
        <strong>{author ? author.full_name : "RCD"}</strong>
        {author && !author.is_member && <span className="muted"> (former member)</span>}{" "}
        <time className="muted" dateTime={message.created_at}>
          {time(message.created_at)}
        </time>
        {message.edited_at && !message.deleted && <span className="muted"> · edited</span>}
        {message.kind === "requirement_post" && (
          <Badge tone="proposed" icon="📄">
            Requirement · Proposed
          </Badge>
        )}
      </header>
      {editing ? (
        <Composer
          label="Edit message"
          members={members}
          initial={segments(message.body, names)
            .map((part) => (part.kind === "text" ? part.text : `@${part.name}`))
            .join("")}
          initialPicked={message.mentions.flatMap((id) => (names.has(id) ? [{ userId: id, name: names.get(id) ?? "" }] : []))}
          submitLabel="Save"
          onCancel={() => setEditing(false)}
          onSend={async (body) => {
            await edit.mutateAsync({ id: message.id, body });
            setEditing(false);
          }}
        />
      ) : (
        <MessageBody message={message} names={names} />
      )}
      <footer className="message-actions">
        {onOpenThread && message.parent_id === null && !message.deleted && (
          <Button variant="ghost" size="sm" onClick={() => onOpenThread(message)}>
            {message.reply_count > 0
              ? `${message.reply_count} ${message.reply_count === 1 ? "reply" : "replies"}`
              : "Reply in thread"}
          </Button>
        )}
        {editable && !editing && (
          <>
            <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button
              variant="ghost"
              size="sm"
              loading={remove.isPending}
              onClick={() => {
                if (window.confirm("Delete this message? Replies stay in the thread.")) remove.mutate(message);
              }}
            >
              Delete
            </Button>
          </>
        )}
      </footer>
    </article>
  );
}
