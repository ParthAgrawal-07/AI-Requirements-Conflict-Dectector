import { Drawer } from "../../components/Drawer";
import { usePostMessage, useThread, type Member, type Message } from "./api";
import { Composer } from "./Composer";
import { MessageItem } from "./MessageItem";

export interface ThreadProps {
  root: Message | null;
  members: Member[];
  canPost: boolean;
  readOnly: boolean; // archived channel
  onClose: () => void;
}

/** A thread in the side drawer (US-29): the first message, its replies, and a reply box. */
export function Thread({ root, members, canPost, readOnly, onClose }: ThreadProps) {
  const thread = useThread(root?.id ?? null);
  const reply = usePostMessage(root?.channel_id ?? "", root?.id ?? null);
  const items = thread.data ?? (root ? [root] : []);

  return (
    <Drawer open={root !== null} title="Thread" onClose={onClose}>
      {thread.isError && <p role="alert">The thread could not be loaded.</p>}
      <div className="thread" role="log" aria-label="Thread messages">
        {items.map((message) => (
          <MessageItem key={message.id} message={message} members={members} canPost={canPost} />
        ))}
      </div>
      {canPost && !readOnly && root && !root.deleted && (
        <Composer label="Reply in thread" members={members} onSend={(body) => reply.mutateAsync(body)} />
      )}
    </Drawer>
  );
}
