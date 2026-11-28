// Live-map freshness (Affan — US-14, NFR-32: a change is on every open map within 2 s of the commit).
//
// k6 script. Every virtual user keeps a map open (a WebSocket subscribed to the demo project) and,
// every few seconds, moves its own requirement with PUT /graph/positions — a layout-only change
// that needs no LLM — then times how long its own graph.delta takes to arrive. Every other open map
// receives that delta too, so the gateway fans out VUS × VUS deltas per round. The lag is counted
// from before the PUT, so it includes the request itself: an upper bound on commit-to-map. VUs
// beyond the number of requirements only listen (two movers of one node would overwrite each
// other's marker).
//
//   docker compose up -d && docker compose exec backend python -m app.cli seed-demo
//   (the demo project needs at least one requirement: upload the planted SRS first)
//   k6 run load/map_freshness.js                        # 20 open maps for 2 minutes
//   k6 run -e VUS=50 -e DURATION=5m -e API_URL=http://staging:8000 load/map_freshness.js
//
// The run fails when the 95th percentile of map_delta_lag is 2 s or more, or a delta is lost.

import http from "k6/http";
import ws from "k6/ws";
import { check, fail } from "k6";
import { Counter, Trend } from "k6/metrics";

const API = __ENV.API_URL || "http://localhost:8000";
const WS = API.replace(/^http/, "ws") + "/ws";
const EMAIL = __ENV.EMAIL || "developer@demo.local"; // needs req.comment to move nodes
const PASSWORD = __ENV.PASSWORD || "demo-password-123";
const MOVE_EVERY_MS = 3_000;
const WAIT_MS = 10_000; // a delta later than this counts as lost

const lag = new Trend("map_delta_lag", true);
const lost = new Counter("map_delta_lost");
const heard = new Counter("map_deltas_received");

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "2m",
  thresholds: {
    map_delta_lag: ["p(95)<2000"],
    map_delta_lost: ["count==0"],
  },
};

function json(response, what) {
  if (response.status !== 200) fail(`${what}: HTTP ${response.status} ${response.body}`);
  return response.json();
}

/** One sign-in for the whole run (the login rate limit would refuse one per VU), and the demo
 *  project's requirements to move. */
export function setup() {
  const login = http.post(`${API}/api/v1/auth/login`, { username: EMAIL, password: PASSWORD });
  const token = json(login, "login").access_token;
  const auth = { headers: { Authorization: `Bearer ${token}` } };
  const workspace = json(http.get(`${API}/api/v1/workspaces`, auth), "workspaces").find(
    (w) => w.name === "Demo Workspace",
  );
  if (!workspace) fail("no Demo Workspace: run seed-demo");
  const project = json(http.get(`${API}/api/v1/workspaces/${workspace.id}/projects`, auth), "projects").find(
    (p) => p.name === "Demo Project",
  );
  if (!project) fail("no Demo Project: run seed-demo");
  const graph = json(http.get(`${API}/api/v1/projects/${project.id}/graph`, auth), "graph");
  if (graph.nodes.length === 0) fail("the demo project has no requirements to move");
  return { token, projectId: project.id, nodeIds: graph.nodes.map((n) => n.id) };
}

export default function (data) {
  const nodeId = __VU <= data.nodeIds.length ? data.nodeIds[__VU - 1] : null;
  const headers = { Authorization: `Bearer ${data.token}`, "Content-Type": "application/json" };
  let round = 0;
  let pending = null; // { x, sentAt }

  const response = ws.connect(WS, {}, (socket) => {
    socket.on("open", () => socket.send(JSON.stringify({ type: "auth", token: data.token })));

    socket.on("message", (raw) => {
      const frame = JSON.parse(raw);
      if (frame.type === "ready") {
        socket.send(JSON.stringify({ type: "subscribe", project_id: data.projectId }));
      } else if (frame.type === "error") {
        fail(`socket refused: ${frame.code}`);
      } else if (frame.type === "event" && frame.event.type === "graph.delta") {
        heard.add(1);
        if (pending === null) return;
        const mine = frame.event.data.changed.nodes.some((n) => n.id === nodeId && n.x === pending.x);
        if (mine) {
          lag.add(Date.now() - pending.sentAt);
          pending = null;
        }
      }
    });

    // A unique x per VU and round marks this VU's own delta among everyone else's.
    socket.setInterval(() => {
      if (nodeId === null) return;
      if (pending !== null && Date.now() - pending.sentAt > WAIT_MS) {
        lost.add(1);
        pending = null;
      }
      if (pending !== null) return;
      round += 1;
      const x = __VU * 10_000 + round;
      const sentAt = Date.now();
      const moved = http.put(
        `${API}/api/v1/projects/${data.projectId}/graph/positions`,
        JSON.stringify({ positions: [{ requirement_id: nodeId, x, y: round % 500 }] }),
        { headers },
      );
      check(moved, { "positions saved (204)": (r) => r.status === 204 });
      if (moved.status === 204) pending = { x, sentAt };
    }, MOVE_EVERY_MS);

    socket.setTimeout(() => socket.close(), durationMs(options.duration) - 1_000);
  });
  check(response, { "socket opened (101)": (r) => r && r.status === 101 });
}

function durationMs(value) {
  const match = /^(\d+)(ms|s|m|h)$/.exec(value);
  if (!match) return 120_000;
  return Number(match[1]) * { ms: 1, s: 1_000, m: 60_000, h: 3_600_000 }[match[2]];
}
