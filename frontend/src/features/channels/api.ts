// Channels and messages (Pranshu — US-28, US-29; API by Madhav and Dhavni, contract in
// docs/contracts/channels.md and docs/contracts/realtime.md).
//
// Query keys: ["channels", projectId] (sidebar, with unread counts), ["messages", channelId]
// (infinite, newest page first), ["thread", rootId], ["members", workspaceId] (mention picker;
// the same key as the Members tab, so they share one cache entry).

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { RoleRef, UUID } from "../../api/types";

export interface Channel {
  id: UUID;
  project_id: UUID;
  name: string;
  topic: string | null;
  is_private: boolean;
  is_default: boolean;
  archived_at: string | null;
  created_by: UUID | null;
  created_at: string;
  unread_count: number;
  last_message_at: string | null;
}

export type MessageKind = "chat" | "requirement_post" | "change_request" | "analysis_card" | "system";

export interface Message {
  id: UUID;
  channel_id: UUID;
  parent_id: UUID | null;
  kind: MessageKind;
  body: string;
  /** null: a system message written by the app (a result card, US-31). */
  author: { id: UUID; full_name: string; is_member: boolean } | null;
  /** A card's ids (run_id, requirement_id…); details are read over REST. */
  payload?: Record<string, unknown> | null;
  mentions: UUID[];
  created_at: string;
  edited_at: string | null;
  deleted: boolean;
  reply_count: number;
  last_reply_at: string | null;
  cursor: string;
}

export interface MessagePage {
  items: Message[]; // oldest first
  next_cursor: string | null; // older messages
}

export interface Member {
  user: { id: UUID; full_name: string; email: string };
  role: RoleRef;
  stakeholder_group: string | null;
  joined_at: string;
}

export interface ChannelInput {
  name: string;
  topic?: string | null;
  is_private: boolean;
  member_ids?: UUID[];
}

export function useChannels(projectId: string | undefined) {
  return useQuery({
    queryKey: ["channels", projectId],
    enabled: Boolean(projectId),
    queryFn: () => apiFetch<Channel[]>(`/projects/${projectId}/channels`),
  });
}

export function useChannel(channelId: string) {
  return useQuery({
    queryKey: ["channel", channelId],
    queryFn: () => apiFetch<Channel>(`/channels/${channelId}`),
  });
}

export function useMembers(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["members", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => apiFetch<Member[]>(`/workspaces/${workspaceId}/members`),
    staleTime: 60_000,
  });
}

export function useCreateChannel(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChannelInput) =>
      apiFetch<Channel>(`/projects/${projectId}/channels`, { method: "POST", json: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["channels", projectId] }),
  });
}

export function useArchiveChannel(channelId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<Channel>(`/channels/${channelId}/archive`, { method: "POST" }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["channel", channelId], updated);
      void queryClient.invalidateQueries({ queryKey: ["channels", projectId] });
    },
  });
}

/** Clears the channel's unread count for the caller (POST /channels/{c}/read). */
export function useMarkRead(channel: Channel | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>(`/channels/${channel?.id}/read`, { method: "POST" }),
    onSuccess: () => {
      if (!channel) return;
      queryClient.setQueryData<Channel[]>(["channels", channel.project_id], (list) =>
        list?.map((item) => (item.id === channel.id ? { ...item, unread_count: 0 } : item)),
      );
    },
  });
}

export function useMessages(channelId: string) {
  return useInfiniteQuery({
    queryKey: ["messages", channelId],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      apiFetch<MessagePage>(`/channels/${channelId}/messages`, {
        query: { before: pageParam, limit: 50 },
        signal,
      }),
    getNextPageParam: (page) => page.next_cursor,
  });
}

export function useThread(rootId: string | null) {
  return useQuery({
    queryKey: ["thread", rootId],
    enabled: Boolean(rootId),
    queryFn: () => apiFetch<Message[]>(`/messages/${rootId}/thread`),
  });
}

export function usePostMessage(channelId: string, parentId: string | null = null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      apiFetch<Message>(`/channels/${channelId}/messages`, {
        method: "POST",
        json: { body, parent_id: parentId },
      }),
    onSuccess: (message) => upsertMessage(queryClient, message),
  });
}

export function useEditMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: UUID; body: string }) =>
      apiFetch<Message>(`/messages/${id}`, { method: "PATCH", json: { body } }),
    onSuccess: (message) => upsertMessage(queryClient, message),
  });
}

export function useDeleteMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (message: Message) =>
      apiFetch<void>(`/messages/${message.id}`, { method: "DELETE" }).then(() => message),
    onSuccess: (message) =>
      upsertMessage(queryClient, { ...message, body: "", deleted: true, mentions: [] }),
  });
}

/** Put a message into whatever cache shows it: the channel history (top-level messages) or its
 *  thread (replies, and the root itself). Used by mutations and by realtime events alike. */
export function upsertMessage(queryClient: QueryClient, message: Message): void {
  if (message.parent_id === null) {
    queryClient.setQueryData<InfiniteData<MessagePage>>(["messages", message.channel_id], (data) => {
      if (!data) return data;
      const exists = data.pages.some((page) => page.items.some((item) => item.id === message.id));
      const pages = data.pages.map((page, index) => {
        if (exists) {
          return { ...page, items: page.items.map((item) => (item.id === message.id ? message : item)) };
        }
        // pages[0] is the newest page; new messages go at its end
        return index === 0 ? { ...page, items: [...page.items, message] } : page;
      });
      return { ...data, pages };
    });
  } else {
    void queryClient.invalidateQueries({ queryKey: ["messages", message.channel_id] }); // reply counts
  }
  const threadKey = ["thread", message.parent_id ?? message.id];
  queryClient.setQueryData<Message[]>(threadKey, (thread) => {
    if (!thread) return thread;
    return thread.some((item) => item.id === message.id)
      ? thread.map((item) => (item.id === message.id ? message : item))
      : [...thread, message];
  });
}
