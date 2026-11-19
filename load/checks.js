// Consequence checks of change requests against 500 requirements (Dhavni, with Affan — NFR-26;
// Checkpoint 2).
//
// k6 script. Set-up fills the load project to 500 requirements (lib.js). Then each of the seven
// contributor accounts opens a change request every 15 s on a requirement of the load project —
// tightening its limit, so the findings delta has rule conflicts to report — and times, from
// before the POST, the change_request.checked event that says its consequence report is ready.
// It then withdraws the request, so the project does not fill up with open ones.
//
//   k6 run load/checks.js                                # 20 members, 7 proposers, 3 minutes
//   k6 run -e VUS=50 -e DURATION=10m -e API_URL=http://staging:8000 load/checks.js
//
// Without a model key the report has no AI narrative (Keval, US-34); the checks themselves are
// deterministic and are what this measures.

import { check } from "k6";
import { Counter, Trend } from "k6/metrics";
import {
  CONTRIBUTORS,
  demoWorkspace,
  durationMs,
  get,
  listen,
  loadProject,
  login,
  seedMap,
  send,
} from "./lib.js";

const OPEN_EVERY_MS = 15_000;
const WAIT_MS = 180_000;

const lag = new Trend("consequence_report_lag", true);
const lost = new Counter("consequence_report_lost");

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "3m",
  setupTimeout: "15m",
  thresholds: {
    consequence_report_lag: ["p(90)<90000"],
    consequence_report_lost: ["count==0"],
  },
};

export function setup() {
  const tokens = CONTRIBUTORS.map(login);
  const projectId = loadProject(tokens[0], demoWorkspace(tokens[0]));
  const graph = seedMap(tokens, projectId);
  return { tokens, projectId, requirementIds: graph.nodes.map((n) => n.id) };
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  const proposer = __VU <= data.tokens.length;
  const pending = new Map(); // change request id → sentAt
  let round = 0;

  const response = listen(token, { project_id: data.projectId }, durationMs(options.duration) - 1_000, {
    onReady(socket) {
      if (!proposer) return;
      socket.setInterval(() => {
        for (const [id, sentAt] of pending) {
          if (Date.now() - sentAt > WAIT_MS) {
            lost.add(1);
            pending.delete(id);
          }
        }
        round += 1;
        const index = (__VU * 37 + round * 11) % data.requirementIds.length;
        const requirement = get(token, `/requirements/${data.requirementIds[index]}`);
        const sentAt = Date.now();
        const opened = send(token, "POST", `/requirements/${requirement.requirement_id}/change-requests`, {
          proposed_body: requirement.body.replace(/within \d+ seconds/, `within ${20 + round} seconds`),
          reason: `Load test ${__VU}-${round}`,
          base_version: requirement.current_version,
        }, 201);
        pending.set(opened.id, sentAt);
      }, OPEN_EVERY_MS);
    },
    onEvent(event) {
      if (event.type !== "change_request.checked" || !pending.has(event.entity_id)) return;
      lag.add(Date.now() - pending.get(event.entity_id));
      pending.delete(event.entity_id);
      send(token, "POST", `/change-requests/${event.entity_id}/withdraw`, {});
    },
  });
  check(response, { "socket opened (101)": (r) => r && r.status === 101 });
}
