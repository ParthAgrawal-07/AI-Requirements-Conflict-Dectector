# Real-time events — contract

| | |
|---|---|
| **Producer** | Dhavni didi (`app/realtime/`, `app/graph/schemas.py`) |
| **Consumers** | Pranshu (`app/socket.ts`, upload progress) · Abhijeet (live map) · Madhav (notifications, S5) · Affan (WebSocket tests) |
| **Stories** | US-03 (S1), US-29 (S2), US-14 (S3) |

## 1. Envelope

```json
{"type": "analysis.progress", "workspace_id": "…", "project_id": "…", "channel_id": null,
 "entity_id": "…", "at": "2026-10-24T10:42:00Z", "data": {}}
```

`data` carries ids, states and numbers — never requirement or message text (CR-04). Events are hints: on any event a
client may re-read the resource over REST, and after a reconnect it **always** re-reads what it shows (missed events
are not replayed).

| `type` | Since | `entity_id` | `data` |
|---|---|---|---|
| `analysis.progress` | S1 | document | `document_id, status (queued/processing/done/failed), progress_percent, stage, error_message` |
| `membership.revoked` | S2 | the user | `user_id` — the gateway closes that user's sockets (4403); other members refresh the member list |
| `analysis.completed` | S2 | analysis run | `run_id, subject_id, status (done/waiting_budget), pairs_total, pairs_failed, checks_total, checks_failed` — re-read findings |
| `channel.created`, `channel.updated` | S2 | channel | `channel_id, private` (+ `archived: true` when archived) — re-read the channel list |
| `channel.member_removed` | S2 | channel | `channel_id, private, user_id` — that user's channel subscription ends at once |
| `message.created`, `message.updated`, `message.deleted` | S2 | message | `message_id, channel_id, parent_id, author_id, mentions (user ids), private` — re-read `GET /messages/{id}` |
| `graph.delta` | S3 | — | `GraphDelta` (`app/graph/schemas.py`): `from_revision, to_revision, added, changed, removed, sentences` |

## 2. Publishing

`app.realtime.bus.publish(event)` — **after** the commit, never inside a transaction; it never raises. Redis pub/sub
channel per workspace: `rcd:events:<workspace_id>`. `REALTIME_BUS=memory` uses an in-process bus (tests, one process).

## 3. Socket protocol (`/ws`)

| Direction | Frame |
|---|---|
| client → | `{"type": "auth", "token": "<JWT>"}` — first frame, within 10 s, else close **4401** |
| ← server | `{"type": "ready", "user_id": "…"}` |
| client → | `{"type": "subscribe", "project_id": "…"}`, `{"type": "subscribe", "workspace_id": "…"}` or `{"type": "subscribe", "channel_id": "…"}` (S2) |
| ← server | `{"type": "subscribed", …}` or `{"type": "error", "code": "not_found"}` (non-member = unknown id) |
| ← server | `{"type": "event", "event": {…envelope…}}` |
| client → / ← | `{"type": "ping"}` / `{"type": "pong"}` (every 25 s keeps proxies from idling the socket out) |

Membership is re-read on every `subscribe`, as on every REST request. A workspace subscription receives every event of
the workspace; a project subscription receives that project's events and workspace-level ones; a channel subscription
receives that channel's events.

**Private channels (S2).** An event with `channel_id` and `data.private = true` reaches **only** sockets subscribed to
that channel by id, and a `channel_id` subscription to a private channel is checked against its member list (someone
not listed gets `not_found`). A project subscription never receives a private channel's events. A
`channel.member_removed` for the socket's user drops that channel subscription immediately.

**Catching up (S2).** Each message carries a `cursor`. After a reconnect the client calls
`GET /channels/{c}/messages?after=<cursor of the newest message it holds>` — nothing is lost (US-29).

## 4. Progress stages (US-03)

| Stage | `status` | `progress_percent` |
|---|---|---|
| uploaded | `queued` | 0 |
| claimed by the worker, extracting | `processing` (`stage: extraction`) | 10 |
| text extracted, saving | `processing` (`stage: persistence`) | 60 |
| finished | `done` | 100 |
| failed | `failed` (`stage` = where, `error_message` = `[stage] reason`) | 0 |

## 5. Queues

`documents.*` → `documents`; `embeddings.*`, `classification.*`, `analysis.*` → `analysis`; everything else →
`celery`. Compose runs one worker on all three and one `beat` (periodic jobs: join-code expiry; later the budget reset).
