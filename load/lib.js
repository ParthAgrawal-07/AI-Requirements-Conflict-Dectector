// Shared set-up for the Checkpoint 2 load tests (Dhavni, with Affan — NFR-24 to NFR-26, NFR-32,
// NFR-33): sign-in, the demo workspace, the 500-requirement load project and one live socket.
//
// Every script needs `python -m app.cli seed-demo` (one account per default role, one password).
// Event lags are measured from the event's `at` (stamped by the API when it publishes, after the
// commit) to its arrival, so k6 and the API must share a clock: the same host, or NTP-synced.

import http from "k6/http";
import ws from "k6/ws";
import { fail, sleep } from "k6";

export const API = __ENV.API_URL || "http://localhost:8000";
export const WS = API.replace(/^http/, "ws") + "/ws";
const PASSWORD = __ENV.PASSWORD || "demo-password-123";

// Members who may post and open change requests (seed-demo: one account per role; not the Viewer).
export const CONTRIBUTORS = [
  "owner",
  "admin",
  "project.manager",
  "business.analyst",
  "developer",
  "qa.engineer",
  "stakeholder",
].map((role) => `${role}@demo.local`);

export const LOAD_PROJECT = __ENV.LOAD_PROJECT || "Load test (500)";
export const MAP_NODES = 500;
const GROUP = 10; // requirements per subject: every pair in a group breaks the numeric-limit rule
export const MAP_EDGES = (MAP_NODES / GROUP) * ((GROUP * (GROUP - 1)) / 2); // 2,250

export function login(email) {
  const response = http.post(`${API}/api/v1/auth/login`, { username: email, password: PASSWORD });
  if (response.status !== 200) fail(`login ${email}: HTTP ${response.status} ${response.body}`);
  return response.json().access_token;
}

function params(token) {
  return { headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } };
}

function answer(response, expected, what) {
  if (response.status !== expected) fail(`${what}: HTTP ${response.status} ${response.body}`);
  return response.body ? response.json() : null;
}

export const get = (token, path) => answer(http.get(`${API}/api/v1${path}`, params(token)), 200, `GET ${path}`);
export const send = (token, method, path, body, expected = 200) =>
  answer(http.request(method, `${API}/api/v1${path}`, JSON.stringify(body), params(token)), expected, `${method} ${path}`);

const items = (page) => (Array.isArray(page) ? page : page.items);

export function demoWorkspace(token) {
  const workspace = get(token, "/workspaces").find((w) => w.name === "Demo Workspace");
  if (!workspace) fail("no Demo Workspace: run seed-demo");
  return workspace.id;
}

export function projectNamed(token, workspaceId, name) {
  return items(get(token, `/workspaces/${workspaceId}/projects?limit=100`)).find((p) => p.name === name) || null;
}

export function generalChannel(token, projectId) {
  return items(get(token, `/projects/${projectId}/channels`)).find((c) => c.is_default).id;
}

/** The load project, created and activated on first use. Its similarity threshold is 0.95 so no
 *  pair waits for a model in a rules-only stack: the edges come from rule checks. */
export function loadProject(ownerToken, workspaceId) {
  const found = projectNamed(ownerToken, workspaceId, LOAD_PROJECT);
  if (found) return found.id;
  const project = send(ownerToken, "POST", `/workspaces/${workspaceId}/projects`, {
    name: LOAD_PROJECT,
    similarity_threshold: 0.95,
  }, 201);
  send(ownerToken, "PUT", `/projects/${project.id}/context`, {
    fields: {
      purpose: "Load testing the live analysis, checks and map at 500 requirements.",
      scope_in: "Synthetic service-level requirements.",
      scope_out: "Anything a person would read.",
      actors: ["Load generator"],
      environment: "A test stack seeded with seed-demo.",
    },
  });
  return project.id;
}

export function post(token, projectId, statement) {
  return send(token, "POST", `/projects/${projectId}/requirements`, {
    fields: { template: "free_text", slots: { statement }, type: "non_functional", priority: "should", tags: [], acceptance_criteria: [] },
  }, 201);
}

const SUBJECTS = ("billing search checkout catalogue inventory payments refunds invoices ledger payroll " +
  "booking calendar messaging profile reporting export import audit consent identity " +
  "pricing shipping returns loyalty coupons reviews ratings wishlist basket tracking " +
  "warehouse supplier procurement contracts tenders claims policy quotes renewals onboarding " +
  "ticketing routing scheduling dispatch telemetry alerting metering licensing storage archive").split(" ");

/** Fill the load project up to 500 requirements in 50 subjects of 10, then wait for the rule
 *  checks to link every group: 2,250 edges. Each subject has one poster (`tokens` round-robin), so
 *  no pair has two owners and no auto issues open; posts are limited per member per minute (US-29),
 *  so each poster sends 25 a minute. Needs `setupTimeout` of several minutes. */
export function seedMap(tokens, projectId) {
  const have = get(tokens[0], `/projects/${projectId}/graph`).nodes.length;
  const queues = tokens.map(() => []);
  for (let i = have; i < MAP_NODES; i++) {
    const group = Math.floor(i / GROUP);
    const statement = `The ${SUBJECTS[group]} service shall respond within ${(i % GROUP) + 1} seconds.`;
    const token = tokens[group % tokens.length];
    queues[group % tokens.length].push(["POST", `${API}/api/v1/projects/${projectId}/requirements`, JSON.stringify({
      fields: { template: "free_text", slots: { statement }, type: "non_functional", priority: "should", tags: [], acceptance_criteria: [] },
    }), params(token)]);
  }
  while (queues.some((queue) => queue.length > 0)) {
    const round = queues.flatMap((queue) => queue.splice(0, 25));
    for (let i = 0; i < round.length; i += 10) {
      http.batch(round.slice(i, i + 10)).forEach((r) => answer(r, 201, "seed post"));
    }
    if (queues.some((queue) => queue.length > 0)) sleep(61);
  }
  for (let waited = 0; waited < 600; waited += 5) {
    const graph = get(tokens[0], `/projects/${projectId}/graph`);
    if (graph.nodes.length >= MAP_NODES && graph.edges.length >= MAP_EDGES) return graph;
    sleep(5);
  }
  fail(`the load project did not reach ${MAP_NODES} nodes and ${MAP_EDGES} edges in 10 minutes`);
}

/** One socket for the VU: signs in, subscribes, then hands every event to `onEvent` until the
 *  run's duration is up. `onReady(socket)` runs once the subscription is confirmed. */
export function listen(token, subscription, durationMs, { onReady, onEvent }) {
  return ws.connect(WS, {}, (socket) => {
    socket.on("open", () => socket.send(JSON.stringify({ type: "auth", token })));
    socket.on("message", (raw) => {
      const frame = JSON.parse(raw);
      if (frame.type === "ready") socket.send(JSON.stringify({ type: "subscribe", ...subscription }));
      else if (frame.type === "subscribed" && onReady) onReady(socket);
      else if (frame.type === "error") fail(`socket refused: ${frame.code}`);
      else if (frame.type === "event") onEvent(frame.event, socket);
    });
    socket.setTimeout(() => socket.close(), durationMs);
  });
}

/** Milliseconds since the API published `event`. */
export const sincePublished = (event) => Date.now() - Date.parse(event.at);

export function durationMs(value) {
  const match = /^(\d+)(ms|s|m|h)$/.exec(value);
  if (!match) return 120_000;
  return Number(match[1]) * { ms: 1, s: 1_000, m: 60_000, h: 3_600_000 }[match[2]];
}
