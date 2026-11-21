// Chat delivery with 50 connected members (Dhavni, with Affan — NFR-24; Checkpoint 2).
//
// k6 script. Every virtual user is a member with a socket subscribed to the demo project's
// #general; the first seven (one per contributor account — messages are limited per member per
// minute, US-29) each send a message every 4 s. Every socket times every message.created it
// receives from the moment the API published it; each sender also times its own message from
// before the POST, which includes the request.
//
//   k6 run load/messages.js                              # 50 members for 2 minutes
//   k6 run -e VUS=100 -e DURATION=5m -e API_URL=http://staging:8000 load/messages.js
//
// The run fails when message_delivery_lag is 1 s or more at p95, or a sender never hears its own
// message.

import { check } from "k6";
import { Counter, Trend } from "k6/metrics";
import {
  CONTRIBUTORS,
  demoWorkspace,
  durationMs,
  generalChannel,
  listen,
  login,
  projectNamed,
  send,
  sincePublished,
} from "./lib.js";

const SEND_EVERY_MS = 4_000;
const WAIT_MS = 10_000;

const delivery = new Trend("message_delivery_lag", true);
const roundTrip = new Trend("message_round_trip", true);
const delivered = new Counter("messages_delivered");
const lost = new Counter("messages_lost");

export const options = {
  vus: Number(__ENV.VUS || 50),
  duration: __ENV.DURATION || "2m",
  thresholds: {
    message_delivery_lag: ["p(95)<1000"],
    messages_lost: ["count==0"],
  },
};

export function setup() {
  const tokens = CONTRIBUTORS.map(login);
  const project = projectNamed(tokens[0], demoWorkspace(tokens[0]), "Demo Project");
  return { tokens, channelId: generalChannel(tokens[0], project.id) };
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  const sender = __VU <= data.tokens.length;
  let pending = null; // { id, sentAt }
  let round = 0;

  const response = listen(token, { channel_id: data.channelId }, durationMs(options.duration) - 1_000, {
    onReady(socket) {
      if (!sender) return;
      socket.setInterval(() => {
        if (pending !== null && Date.now() - pending.sentAt > WAIT_MS) {
          lost.add(1);
          pending = null;
        }
        if (pending !== null) return;
        round += 1;
        const sentAt = Date.now();
        const message = send(token, "POST", `/channels/${data.channelId}/messages`, { body: `load ${__VU}-${round}` }, 201);
        pending = { id: message.id, sentAt };
      }, SEND_EVERY_MS);
    },
    onEvent(event) {
      if (event.type !== "message.created") return;
      delivered.add(1);
      delivery.add(sincePublished(event));
      if (pending !== null && event.data.message_id === pending.id) {
        roundTrip.add(Date.now() - pending.sentAt);
        pending = null;
      }
    },
  });
  check(response, { "socket opened (101)": (r) => r && r.status === 101 });
}
