// The one WebSocket of the tab (Pranshu — US-03; protocol in docs/contracts/realtime.md).
//
// Components never open sockets: they call useProjectRealtime(projectId), and events update the
// TanStack Query cache. Events are hints — after every (re)connect the cache is invalidated so
// the screen re-reads over REST, because events missed while offline are never replayed.

import { createContext, createElement, useContext, useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { API_BASE_URL } from "../api/client";
import type { RealtimeEvent } from "../api/types";

export type EventHandler = (event: RealtimeEvent) => void;

type SocketLike = Pick<WebSocket, "send" | "close" | "readyState"> & {
  onopen: ((this: WebSocket, ev: Event) => unknown) | null;
  onmessage: ((this: WebSocket, ev: MessageEvent) => unknown) | null;
  onclose: ((this: WebSocket, ev: CloseEvent) => unknown) | null;
};

export type SocketFactory = (url: string) => SocketLike;

const PING_MS = 25_000;
const MAX_BACKOFF_MS = 30_000;
const CLOSE_UNAUTHENTICATED = 4401;
const CLOSE_REVOKED = 4403;

export function realtimeUrl(base: string = API_BASE_URL): string {
  const url = new URL("/ws", base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export class RealtimeConnection {
  private socket: SocketLike | null = null;
  private token: string | null = null;
  private attempts = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private readonly projects = new Map<string, number>(); // project id -> subscriber count
  private readonly handlers = new Set<EventHandler>();
  private readonly resyncHandlers = new Set<() => void>();

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
    this.sendSubscribe(projectId);
    return () => {
      const count = (this.projects.get(projectId) ?? 1) - 1;
      if (count <= 0) this.projects.delete(projectId);
      else this.projects.set(projectId, count);
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

  private open(): void {
    if (!this.token) return;
    this.socket?.close();
    const socket = this.factory(this.url);
    this.socket = socket;
    socket.onopen = () => socket.send(JSON.stringify({ type: "auth", token: this.token }));
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
      for (const projectId of this.projects.keys()) this.sendSubscribe(projectId);
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
    if (!this.token || code === CLOSE_UNAUTHENTICATED || code === CLOSE_REVOKED) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.attempts);
    this.attempts += 1;
    this.retryTimer = setTimeout(() => this.open(), delay);
  }

  private sendSubscribe(projectId: string): void {
    if (this.socket && this.socket.readyState === 1) {
      this.socket.send(JSON.stringify({ type: "subscribe", project_id: projectId }));
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
  const ref = useRef<RealtimeConnection>(connection ?? new RealtimeConnection());
  const realtime = ref.current;

  useEffect(() => {
    if (!token) return;
    realtime.connect(token);
    const stopEvents = realtime.onEvent((event) => applyEvent(queryClient, event));
    const stopResync = realtime.onResync(() => void queryClient.invalidateQueries());
    return () => {
      stopEvents();
      stopResync();
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
