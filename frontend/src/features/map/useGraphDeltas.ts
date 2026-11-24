// Keeps the map's snapshot current from graph.delta events (Abhijeet — US-14, NFR-32, NFR-33).
//
// Deltas that arrive within 250 ms are applied together, in revision order, in one cache update —
// one re-render of a 500-node map instead of one per event. A delta that does not follow the
// revision held (a missed or reordered event) makes the map re-fetch the snapshot: never a wrong
// map, at worst one reload. Each delta's sentences go to the written feed under the map, and the
// elements it touched pulse for 3 s; a layout-only delta (no sentences) neither pulses nor toasts.

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { RealtimeEvent } from "../../api/types";
import { useAuth } from "../../app/auth";
import { useRealtimeEvents } from "../../app/socket";
import { useToast } from "../../components/Toast";
import { applyDelta, graphKey, type GraphDelta, type GraphSnapshot } from "./api";

export const COALESCE_MS = 250;
export const PULSE_MS = 3_000;
const FEED_SIZE = 50;

export interface FeedItem {
  key: string;
  at: string;
  actor: string | null;
  sentence: string;
  elementIds: string[];
}

/** Apply a batch in revision order; deltas the snapshot already includes are skipped. Null when
 *  there is a gap. */
export function applyAll(snapshot: GraphSnapshot, deltas: GraphDelta[]): GraphSnapshot | null {
  let current: GraphSnapshot | null = snapshot;
  for (const delta of [...deltas].sort((a, b) => a.from_revision - b.from_revision)) {
    if (current === null) return null;
    if (delta.to_revision <= current.revision) continue;
    current = applyDelta(current, delta);
  }
  return current;
}

export function touched(delta: GraphDelta): string[] {
  return [
    ...delta.added.nodes.map((n) => n.id),
    ...delta.changed.nodes.map((n) => n.id),
    ...delta.added.edges.map((e) => e.id),
    ...delta.changed.edges.map((e) => e.id),
  ];
}

export function isGraphDelta(event: RealtimeEvent, projectId: string): boolean {
  return event.type === "graph.delta" && event.project_id === projectId;
}

export function useGraphDeltas(projectId: string) {
  const queryClient = useQueryClient();
  const notify = useToast();
  const { user } = useAuth();
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [pulsing, setPulsing] = useState<ReadonlySet<string>>(new Set());
  const buffer = useRef<GraphDelta[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pulseTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const flush = useCallback(() => {
    timer.current = null;
    const batch = buffer.current;
    buffer.current = [];
    const current = queryClient.getQueryData<GraphSnapshot>(graphKey(projectId));
    if (current) {
      const next = applyAll(current, batch);
      if (next === null) void queryClient.invalidateQueries({ queryKey: graphKey(projectId) });
      else queryClient.setQueryData(graphKey(projectId), next);
    }
    const spoken = batch.filter((delta) => delta.sentences.length > 0);
    if (spoken.length === 0) return;

    const items = spoken.flatMap((delta) =>
      delta.sentences.map((sentence, index) => ({
        key: `${delta.to_revision}-${index}`,
        at: new Date().toISOString(),
        actor: delta.actor_name,
        sentence,
        elementIds: touched(delta),
      })),
    );
    setFeed((previous) => [...items.reverse(), ...previous].slice(0, FEED_SIZE));
    const ids = spoken.flatMap(touched);
    setPulsing((previous) => new Set([...previous, ...ids]));
    pulseTimers.current.push(
      setTimeout(() => {
        setPulsing((previous) => new Set([...previous].filter((id) => !ids.includes(id))));
      }, PULSE_MS),
    );
    const last = spoken[spoken.length - 1];
    if (last.actor_id !== user?.id) notify(last.sentences[last.sentences.length - 1]);

    // The drawer and the findings list show what the map shows.
    for (const delta of spoken) {
      for (const node of [...delta.added.nodes, ...delta.changed.nodes]) {
        void queryClient.invalidateQueries({ queryKey: ["requirement", node.id] });
      }
    }
    if (spoken.some((delta) => delta.added.edges.length || delta.changed.edges.length || delta.removed.edge_ids.length)) {
      void queryClient.invalidateQueries({ queryKey: ["findings", projectId] });
    }
    // US-55: every spoken delta is now a row of the written change log;
    // a merge may add a point to the time slider (US-50).
    void queryClient.invalidateQueries({ queryKey: ["changes", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["graph-revisions", projectId] });
  }, [queryClient, projectId, notify, user?.id]);

  useRealtimeEvents((event) => {
    if (!isGraphDelta(event, projectId)) return;
    buffer.current.push(event.data as unknown as GraphDelta);
    if (timer.current === null) timer.current = setTimeout(flush, COALESCE_MS);
  });

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      pulseTimers.current.forEach(clearTimeout);
    },
    [],
  );

  return { feed, pulsing };
}
