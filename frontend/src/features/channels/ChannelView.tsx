import { useEffect } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useChannelRealtime } from "../../app/socket";
import { usePermissions } from "../../app/usePermissions";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import {
  useArchiveChannel,
  useChannel,
  useMarkRead,
  useMembers,
  useMessages,
  usePostMessage,
  type Message,
} from "./api";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import { Thread } from "./Thread";

/** One channel (US-28, US-29; interface design §10): history, composer and the thread drawer
 *  (``?thread=<message id>``, so a thread can be linked). Archived channels are read-only. */
export function ChannelView() {
  const { workspaceId = "", projectId = "", channelId = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  useChannelRealtime(channelId);
  const channel = useChannel(channelId);
  const members = useMembers(workspaceId).data ?? [];
  const messages = useMessages(channelId);
  const { can } = usePermissions({ projectId });
  const post = usePostMessage(channelId);
  const markRead = useMarkRead(channel.data);
  const archive = useArchiveChannel(channelId, projectId);
  const toast = useToast();

  const newestPage = messages.data?.pages[0]?.items ?? [];
  const newest = newestPage[newestPage.length - 1]?.id;
  const loaded = Boolean(channel.data);
  useEffect(() => {
    if (loaded) markRead.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per newest message
  }, [loaded, channelId, newest]);

  if (channel.isError) {
    const missing = channel.error instanceof ApiError && channel.error.status === 404;
    return (
      <div className="page">
        <p role="alert">{missing ? "This channel does not exist or is private." : "The channel could not be loaded."}</p>
      </div>
    );
  }
  if (!channel.data) return <p className="page muted">Loading…</p>;

  const current = channel.data;
  const archived = current.archived_at !== null;
  const canPost = can("message.post");
  const threadId = search.get("thread");
  const allMessages = messages.data?.pages.flatMap((page) => page.items) ?? [];
  const root = threadId ? (allMessages.find((m) => m.id === threadId) ?? null) : null;
  const openThread = (message: Message) => setSearch({ thread: message.id });

  return (
    <div className="channel-view">
      <header className="channel-header">
        <h1>
          <span aria-hidden="true">{current.is_private ? "🔒" : "#"}</span> {current.name}
          <span className="sr-only">{current.is_private ? " (private channel)" : " channel"}</span>
        </h1>
        {current.is_private && <Badge tone="neutral" icon="🔒">Private</Badge>}
        {current.topic && <p className="muted channel-topic">{current.topic}</p>}
        <div className="topbar-spacer" />
        {can("channel.manage") && !archived && !current.is_default && (
          <Button
            variant="ghost"
            size="sm"
            loading={archive.isPending}
            onClick={() => {
              if (!window.confirm(`Archive #${current.name}? It becomes read-only.`)) return;
              archive.mutate(undefined, { onError: (e) => toast(e.message, "error") });
            }}
          >
            Archive
          </Button>
        )}
      </header>
      {archived && (
        <p className="banner" role="status">
          This channel is archived: you can read it, but nobody can post.
        </p>
      )}
      <MessageList channelId={channelId} members={members} canPost={canPost && !archived} onOpenThread={openThread} />
      {canPost && !archived && (
        <Composer label={`Message #${current.name}`} members={members} onSend={(body) => post.mutateAsync(body)} />
      )}
      <Thread
        root={root}
        members={members}
        canPost={canPost}
        readOnly={archived}
        onClose={() => setSearch({})}
      />
    </div>
  );
}
