// The live map at 500 requirements (Dhavni, with Affan — NFR-32, NFR-33; Checkpoint 2).
//
// k6 script. Set-up fills the load project to 500 requirements and ~2,250 rule-check edges (see
// lib.js). Then every virtual user keeps that map open; posters add a requirement every 15 s — a
// real data change, unlike map_freshness.js, which moves nodes — and every open map times the
// graph.delta that adds it. Like the map page, each viewer loads the snapshot once and then only
// applies deltas; RELOAD_EVERY_S makes every viewer download it again that often, as if all the
// browsers reconnected (a stress case, off by default).
//
//   k6 run load/map.js                                   # 50 open maps, 7 posters, 3 minutes
//   k6 run -e RELOAD_EVERY_S=30 load/map.js              # ...and every map reloads every 30 s
//   k6 run -e VUS=100 -e DURATION=5m -e API_URL=http://staging:8000 load/map.js
//
// Measured: map_delta_lag (publish → every open map, NFR-32: p95 < 2 s), map_commit_to_map (the
// poster's own map, from before the POST: an upper bound), map_snapshot (GET /graph at 500 nodes
// and 2,000+ edges). NFR-33 itself — no frame over 100 ms while panning that map — is a browser
// measurement; the report says how it was taken.

import { check } from "k6";
import http from "k6/http";
import { Counter, Trend } from "k6/metrics";
import {
  API,
  CONTRIBUTORS,
  MAP_EDGES,
  MAP_NODES,
  demoWorkspace,
  durationMs,
  listen,
  loadProject,
  login,
  post,
  seedMap,
  sincePublished,
} from "./lib.js";

const POST_EVERY_MS = 15_000;
const RELOAD_EVERY_MS = Number(__ENV.RELOAD_EVERY_S || 0) * 1_000;
const WAIT_MS = 10_000; // a delta later than this counts as lost

const lag = new Trend("map_delta_lag", true);
const commitToMap = new Trend("map_commit_to_map", true);
const snapshot = new Trend("map_snapshot", true);
const lost = new Counter("map_delta_lost");

export const options = {
  vus: Number(__ENV.VUS || 50),
  duration: __ENV.DURATION || "3m",
  setupTimeout: "15m",
  thresholds: {
    map_delta_lag: ["p(95)<2000"],
    map_delta_lost: ["count==0"],
    map_snapshot: ["p(95)<2000"], // NFR-02: a synchronous read within 2 s
  },
};

export function setup() {
  const tokens = CONTRIBUTORS.map(login);
  const projectId = loadProject(tokens[0], demoWorkspace(tokens[0]));
  const graph = seedMap(tokens, projectId);
  console.log(`map: ${graph.nodes.length} nodes, ${graph.edges.length} edges`);
  return { tokens, projectId };
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  const poster = __VU <= data.tokens.length; // one poster per member: posts are rate-limited per member
  const headers = { headers: { Authorization: `Bearer ${token}` } };
  let pending = null; // { id, sentAt }
  let round = 0;

  const response = listen(token, { project_id: data.projectId }, durationMs(options.duration) - 1_000, {
    onReady(socket) {
      const load = () => {
        const started = Date.now();
        const graph = http.get(`${API}/api/v1/projects/${data.projectId}/graph`, headers);
        snapshot.add(Date.now() - started);
        check(graph, {
          "snapshot is the full map": (r) =>
            r.status === 200 && r.json().nodes.length >= MAP_NODES && r.json().edges.length >= MAP_EDGES,
        });
      };
      load();
      if (RELOAD_EVERY_MS > 0) socket.setInterval(load, RELOAD_EVERY_MS);
      if (!poster) return;
      socket.setInterval(() => {
        if (pending !== null && Date.now() - pending.sentAt > WAIT_MS) {
          lost.add(1);
          pending = null;
        }
        if (pending !== null) return;
        round += 1;
        const sentAt = Date.now();
        const posted = post(token, data.projectId, `The map probe ${__VU}-${round} shall be shown within 2 seconds.`);
        pending = { id: posted.requirement.requirement_id, sentAt };
      }, POST_EVERY_MS);
    },
    onEvent(event) {
      if (event.type !== "graph.delta" || event.data.added.nodes.length === 0) return;
      lag.add(sincePublished(event));
      if (pending !== null && event.data.added.nodes.some((node) => node.id === pending.id)) {
        commitToMap.add(Date.now() - pending.sentAt);
        pending = null;
      }
    },
  });
  check(response, { "socket opened (101)": (r) => r && r.status === 101 });
}
