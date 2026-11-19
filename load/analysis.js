// Live analysis of posts against 500 requirements (Dhavni, with Affan — NFR-25; Checkpoint 2).
//
// k6 script. Set-up fills the load project to 500 requirements (lib.js). Then each of the seven
// contributor accounts posts a requirement every 10 s — each one shares a subject and metric with
// ten others, so the rule checks have real work — and times, from before the POST, the
// analysis.completed event of the post's run: what makes the result card appear in the thread.
// Other virtual users only keep the project open, so the events fan out as they would in use.
//
//   k6 run load/analysis.js                              # 20 members, 7 posters, 3 minutes
//   k6 run -e VUS=50 -e DURATION=10m -e API_URL=http://staging:8000 load/analysis.js
//
// NFR-25 excludes time spent waiting for the AI budget; a run parked for budget is counted in
// analysis_waiting_budget, not in the lag. Without a model key the run has no AI work: the lag is
// embedding, candidates and rule checks only (the report says which kind of stack it ran on).

import { check } from "k6";
import { Counter, Trend } from "k6/metrics";
import {
  CONTRIBUTORS,
  demoWorkspace,
  durationMs,
  listen,
  loadProject,
  login,
  post,
  seedMap,
} from "./lib.js";

const POST_EVERY_MS = 10_000;
const WAIT_MS = 120_000;
const SUBJECTS = ["billing", "search", "checkout", "ledger", "payroll", "booking", "export"];

const lag = new Trend("result_card_lag", true);
const parked = new Counter("analysis_waiting_budget");
const lost = new Counter("result_card_lost");

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "3m",
  setupTimeout: "15m",
  thresholds: {
    result_card_lag: ["p(90)<60000"],
    result_card_lost: ["count==0"],
  },
};

export function setup() {
  const tokens = CONTRIBUTORS.map(login);
  const projectId = loadProject(tokens[0], demoWorkspace(tokens[0]));
  seedMap(tokens, projectId);
  return { tokens, projectId };
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  const poster = __VU <= data.tokens.length;
  const pending = new Map(); // run id → sentAt
  let round = 0;

  const response = listen(token, { project_id: data.projectId }, durationMs(options.duration) - 1_000, {
    onReady(socket) {
      if (!poster) return;
      socket.setInterval(() => {
        for (const [runId, sentAt] of pending) {
          if (Date.now() - sentAt > WAIT_MS) {
            lost.add(1);
            pending.delete(runId);
          }
        }
        round += 1;
        const subject = SUBJECTS[(__VU + round) % SUBJECTS.length];
        const sentAt = Date.now();
        const posted = post(token, data.projectId, `The ${subject} service shall respond within ${10 + round} seconds.`);
        pending.set(posted.analysis_run_id, sentAt);
      }, POST_EVERY_MS);
    },
    onEvent(event) {
      if (event.type !== "analysis.completed" || !pending.has(event.data.run_id)) return;
      if (event.data.status === "waiting_budget") {
        parked.add(1);
      } else {
        lag.add(Date.now() - pending.get(event.data.run_id));
      }
      pending.delete(event.data.run_id);
    },
  });
  check(response, { "socket opened (101)": (r) => r && r.status === 101 });
}
