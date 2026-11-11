// The one WebSocket of the tab (Pranshu — US-03, US-29; protocol in docs/contracts/realtime.md).
//
// Components never open sockets: they call useProjectRealtime(projectId) or
// useChannelRealtime(channelId), and events update the TanStack Query cache. Events are hints —
// after every (re)connect the cache is invalidated so the screen re-reads over REST, because
// events missed while offline are never replayed.

import { createContext, createElement, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  API_BASE_URL,
  apiFetch,
  getAccessToken,
  refreshAccessToken,
  triggerUnauthorized,
} from "../api/client";
import type { RealtimeEvent } from "../api/types";
import { upsertMessage, type Message } from "../features/channels/api";

export type EventHandler = (event: RealtimeEvent) => void;

type SocketLike = Pick<WebSocket, "send" | "close" | "readyState"> & {
  onopen: ((this: WebSocket, ev: Event) => unknown) | null;
  onmessage: ((this: WebSocket, ev: MessageEvent) => unknown) | null;
  onclose: ((this: WebSocket, ev: CloseEvent) => unknown) | null;
};

export type SocketFactory = (url: string) => SocketLike;

const PING_MS = 25_000;
const MAX_BACKOFF_MS = 30_000;
const MAX_ATTEMPTS = 5;
const CLOSE_UNAUTHENTICATED = 4401;
const CLOSE_REVOKED = 4403;

const REALTIME_ENABLED =
  typeof import.meta !== "undefined" && import.meta.env
    ? import.meta.env.VITE_REALTIME_ENABLED !== "false"
    : true;

export function realtimeUrl(base: string = API_BASE_URL): string {
  const url = new URL("/ws", base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export class RealtimeConnection {
  private socket: SocketLike | null = null;
  private token: string | null = null;
  private attempts = 0;
  private refreshedSinceReady = false;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private readonly projects = new Map<string, number>(); // project id -> subscriber count
  private readonly channels = new Map<string, number>(); // channel id -> subscriber count
  private readonly handlers = new Set<EventHandler>();
  private readonly resyncHandlers = new Set<() => void>();
  private readonly revokedHandlers = new Set<() => void>();

  constructor(
    private readonly url: string = realtimeUrl(),
    private readonly factory: SocketFactory = (u) => new WebSocket(u),
  ) {}

  connect(token: string): void {
    this.token = token;
    this.attempts = 0;
    this.open();
  }

  disconnect(): void {
    this.token = null;
    this.clearTimers();
    this.socket?.close();
    this.socket = null;
  }

  /** Watch a project's events; returns the function that stops watching. */
  watchProject(projectId: string): () => void {
    this.projects.set(projectId, (this.projects.get(projectId) ?? 0) + 1);
    this.sendSubscribe(projectId, "project_id");
    return () => {
      const count = (this.projects.get(projectId) ?? 1) - 1;
      if (count <= 0) {
        this.projects.delete(projectId);
        this.sendUnsubscribe(projectId, "project_id");
      } else {
        this.projects.set(projectId, count);
      }
    };
  }

  /** Watch one channel (US-29): private channels' events only reach sockets subscribed by id. */
  watchChannel(channelId: string): () => void {
    this.channels.set(channelId, (this.channels.get(channelId) ?? 0) + 1);
    this.sendSubscribe(channelId, "channel_id");
    return () => {
      const count = (this.channels.get(channelId) ?? 1) - 1;
      if (count <= 0) {
        this.channels.delete(channelId);
        this.sendUnsubscribe(channelId, "channel_id");
      } else {
        this.channels.set(channelId, count);
      }
    };
  }

  onEvent(handler: EventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  /** Called after every successful (re)connect: re-read what the screen shows. */
  onResync(handler: () => void): () => void {
    this.resyncHandlers.add(handler);
    return () => this.resyncHandlers.delete(handler);
  }

  onRevoked(handler: () => void): () => void {
    this.revokedHandlers.add(handler);
    return () => this.revokedHandlers.delete(handler);
  }

  private open(): void {
    if (!REALTIME_ENABLED || !this.token) return;
    this.socket?.close();
    const socket = this.factory(this.url);
    this.socket = socket;
    // The client's token is the freshest one: apiFetch may have refreshed it since connect().
    const token = getAccessToken() ?? this.token;
    socket.onopen = () => socket.send(JSON.stringify({ type: "auth", token }));
    socket.onmessage = (message) => this.receive(String(message.data));
    socket.onclose = (event) => this.closed(socket, event.code);
  }

  private receive(raw: string): void {
    let frame: { type?: string; event?: RealtimeEvent };
    try {
      frame = JSON.parse(raw);
    } catch {
      return;
    }
    if (frame.type === "ready") {
      this.attempts = 0;
      this.refreshedSinceReady = false;
      for (const projectId of this.projects.keys()) this.sendSubscribe(projectId, "project_id");
      for (const channelId of this.channels.keys()) this.sendSubscribe(channelId, "channel_id");
      this.startPing();
      this.resyncHandlers.forEach((handler) => handler());
    } else if (frame.type === "event" && frame.event) {
      const event = frame.event;
      this.handlers.forEach((handler) => handler(event));
    }
  }

  private closed(socket: SocketLike, code: number): void {
    if (socket !== this.socket) return; // an old socket we replaced
    this.clearTimers();
    this.socket = null;
    if (code === CLOSE_UNAUTHENTICATED) {
      void this.reauthenticate();
      return;
    }
    if (code === CLOSE_REVOKED) {
      this.revokedHandlers.forEach((handler) => handler());
      return;
    }
    if (!this.token || this.attempts >= MAX_ATTEMPTS) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.attempts);
    this.attempts += 1;
    this.retryTimer = setTimeout(() => this.open(), delay);
  }

  /** The token expired: refresh once and reconnect, or end the session if that fails too. */
  private async reauthenticate(): Promise<void> {
    const token = this.refreshedSinceReady ? null : await refreshAccessToken();
    if (!token || !this.token) {
      if (this.token) triggerUnauthorized(); // still signed in here, but the session is gone
      return;
    }
    this.refreshedSinceReady = true;
    this.token = token;
    this.open();
  }

  private sendSubscribe(id: string, field: "project_id" | "channel_id" = "project_id"): void {
    if (this.socket && this.socket.readyState === 1) {
      this.socket.send(JSON.stringify({ type: "subscribe", [field]: id }));
    }
  }

  private sendUnsubscribe(id: string, field: "project_id" | "channel_id" = "project_id"): void {
    if (this.socket && this.socket.readyState === 1) {
      this.socket.send(JSON.stringify({ type: "unsubscribe", [field]: id }));
    }
  }

  private startPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = setInterval(() => {
      if (this.socket?.readyState === 1) this.socket.send(JSON.stringify({ type: "ping" }));
    }, PING_MS);
  }

  private clearTimers(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.retryTimer = null;
    this.pingTimer = null;
  }
}

/** How each event type changes the query cache. Keys match features/<area>/api.ts. */
export function applyEvent(queryClient: QueryClient, event: RealtimeEvent): void {
  if (event.type === "analysis.progress" && event.project_id) {
    void queryClient.invalidateQueries({ queryKey: ["documents", event.project_id] });
    if (event.data.status === "done") {
      void queryClient.invalidateQueries({ queryKey: ["requirements", event.project_id] });
    }
  } else if (event.type === "analysis.completed" && event.project_id) {
    void queryClient.invalidateQueries({ queryKey: ["findings", event.project_id] });
  } else if (event.type.startsWith("message.") && event.entity_id) {
    // Ids only in the event (CR-04): re-read the message, which re-checks access, then patch.
    void apiFetch<Message>(`/messages/${event.entity_id}`)
      .then((message) => upsertMessage(queryClient, message))
      .catch(() => undefined);
    if (event.type === "message.created" && event.project_id) {
      void queryClient.invalidateQueries({ queryKey: ["channels", event.project_id] }); // unread
    }
  } else if (event.type.startsWith("channel.") && event.project_id) {
    void queryClient.invalidateQueries({ queryKey: ["channels", event.project_id] });
    if (event.channel_id) void queryClient.invalidateQueries({ queryKey: ["channel", event.channel_id] });
  } else if (event.type === "membership.revoked") {
    void queryClient.invalidateQueries({ queryKey: ["members", event.workspace_id] });
  }
}

const RealtimeContext = createContext<RealtimeConnection | null>(null);

export function RealtimeProvider({
  token,
  children,
  connection,
}: {
  token: string | null;
  children: ReactNode;
  connection?: RealtimeConnection;
}) {
  const queryClient = useQueryClient();
  const [realtime] = useState(() => connection ?? new RealtimeConnection());

  useEffect(() => {
    if (!token) return;
    realtime.connect(token);
    const stopEvents = realtime.onEvent((event) => applyEvent(queryClient, event));
    const stopResync = realtime.onResync(() => void queryClient.invalidateQueries());
    const stopRevoked = realtime.onRevoked(() => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      void queryClient.invalidateQueries({ queryKey: ["permissions"] });
    });
    return () => {
      stopEvents();
      stopResync();
      stopRevoked();
      realtime.disconnect();
    };
  }, [token, realtime, queryClient]);

  return createElement(RealtimeContext.Provider, { value: realtime }, children);
}

/** Keep this project's events flowing into the cache while the calling screen is mounted. */
export function useProjectRealtime(projectId: string | undefined): void {
  const realtime = useContext(RealtimeContext);
  useEffect(() => {
    if (!realtime || !projectId) return;
    return realtime.watchProject(projectId);
  }, [realtime, projectId]);
}

/** Keep this channel's events (including a private channel's) flowing while mounted. */
export function useChannelRealtime(channelId: string | undefined): void {
  const realtime = useContext(RealtimeContext);
  useEffect(() => {
    if (!realtime || !channelId) return;
    return realtime.watchChannel(channelId);
  }, [realtime, channelId]);
}
