import { useEffect, useLayoutEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Button } from "../../components/Button";
import { useMessages, type Member, type Message } from "./api";
import { MessageItem } from "./MessageItem";

export interface MessageListProps {
  channelId: string;
  members: Member[];
  canPost: boolean;
  onOpenThread: (message: Message) => void;
}

// Short histories render plainly; long ones are windowed so the DOM stays small (US-29).
export const VIRTUALIZE_AFTER = 80;
const ESTIMATED_ROW = 72;

/** Channel history, oldest at the top. "Load older messages" pages back with the cursor; the view
 *  stays pinned to the bottom while the reader is at the bottom and new messages arrive. */
export function MessageList({ channelId, members, canPost, onOpenThread }: MessageListProps) {
  const query = useMessages(channelId);
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  // pages[0] is the newest page; each page is oldest-first.
  const messages = [...(query.data?.pages ?? [])].reverse().flatMap((page) => page.items);
  const virtual = messages.length > VIRTUALIZE_AFTER;
  const rows = useVirtualizer({
    count: virtual ? messages.length : 0,
    getScrollElement: () => scroller.current,
    estimateSize: () => ESTIMATED_ROW,
    overscan: 8,
  });

  const last = messages[messages.length - 1]?.id;
  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element || !pinned.current) return;
    if (virtual) rows.scrollToIndex(messages.length - 1, { align: "end" });
    else element.scrollTop = element.scrollHeight;
  }, [last, virtual, messages.length, rows]);

  useEffect(() => {
    pinned.current = true;
  }, [channelId]);

  if (query.isLoading) return <p className="muted">Loading messages…</p>;
  if (query.isError) return <p role="alert">The messages could not be loaded.</p>;

  const item = (message: Message) => (
    <MessageItem message={message} members={members} canPost={canPost} onOpenThread={onOpenThread} />
  );

  return (
    <div
      ref={scroller}
      className="message-list"
      role="log"
      aria-live="polite"
      aria-label="Messages"
      tabIndex={0}
      onScroll={(event) => {
        const element = event.currentTarget;
        pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 48;
      }}
    >
      {query.hasNextPage && (
        <div className="message-list-more">
          <Button
            variant="ghost"
            size="sm"
            loading={query.isFetchingNextPage}
            onClick={() => {
              pinned.current = false;
              void query.fetchNextPage();
            }}
          >
            Load older messages
          </Button>
        </div>
      )}
      {messages.length === 0 && <p className="empty-state">No messages yet. Say hello.</p>}
      {virtual ? (
        <div style={{ height: rows.getTotalSize(), position: "relative" }}>
          {rows.getVirtualItems().map((row) => (
            <div
              key={messages[row.index].id}
              ref={rows.measureElement}
              data-index={row.index}
              style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${row.start}px)` }}
            >
              {item(messages[row.index])}
            </div>
          ))}
        </div>
      ) : (
        messages.map((message) => <div key={message.id}>{item(message)}</div>)
      )}
    </div>
  );
}
