import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { RealtimeConnection, applyEvent, realtimeUrl } from "../src/app/socket";
import type { RealtimeEvent } from "../src/api/types";

class FakeSocket {
  static all: FakeSocket[] = [];
  readyState = 0;
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;

  constructor(readonly url: string) {
    FakeSocket.all.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.readyState = 3;
  }
  // test helpers
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  receive(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
  drop(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

function connection() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return new RealtimeConnection("ws://test/ws", (url) => new FakeSocket(url) as any);
}

const progress: RealtimeEvent = {
  type: "analysis.progress",
  workspace_id: "w",
  project_id: "p",
  channel_id: null,
  entity_id: "d",
  at: "2026-10-24T00:00:00Z",
  data: { status: "done", progress_percent: 100 },
};

beforeEach(() => {
  FakeSocket.all = [];
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("RealtimeConnection", () => {
  it("authenticates in the first frame and subscribes once ready", () => {
    const realtime = connection();
    realtime.watchProject("p");
    realtime.connect("jwt");
    const socket = FakeSocket.all[0];

    socket.open();
    expect(socket.sent[0]).toEqual({ type: "auth", token: "jwt" });
    socket.receive({ type: "ready", user_id: "u" });
    expect(socket.sent).toContainEqual({ type: "subscribe", project_id: "p" });
  });

  it("delivers events to handlers", () => {
    const realtime = connection();
    const handler = vi.fn();
    realtime.onEvent(handler);
    realtime.connect("jwt");
    FakeSocket.all[0].open();
    FakeSocket.all[0].receive({ type: "event", event: progress });
    expect(handler).toHaveBeenCalledWith(progress);
  });

  it("reconnects with backoff, re-subscribes and asks for a REST re-sync", () => {
    const realtime = connection();
    const resync = vi.fn();
    realtime.onResync(resync);
    realtime.watchProject("p");
    realtime.connect("jwt");
    FakeSocket.all[0].open();
    FakeSocket.all[0].receive({ type: "ready" });

    FakeSocket.all[0].drop();
    vi.advanceTimersByTime(1000);
    const second = FakeSocket.all[1];
    second.open();
    second.receive({ type: "ready" });

    expect(second.sent).toContainEqual({ type: "subscribe", project_id: "p" });
    expect(resync).toHaveBeenCalledTimes(2);
  });

  it("does not reconnect after the server revoked the membership", () => {
    const realtime = connection();
    realtime.connect("jwt");
    FakeSocket.all[0].open();
    FakeSocket.all[0].drop(4403);
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.all).toHaveLength(1);
  });

  it("builds the ws URL from the API base", () => {
    expect(realtimeUrl("https://api.example.com")).toBe("wss://api.example.com/ws");
    expect(realtimeUrl("http://localhost:8000")).toBe("ws://localhost:8000/ws");
  });
});

describe("applyEvent", () => {
  it("refreshes documents, and requirements when extraction finished", () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    applyEvent(client, progress);
    expect(spy).toHaveBeenCalledWith({ queryKey: ["documents", "p"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["requirements", "p"] });
  });
});
