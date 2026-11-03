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
| `membership.revoked` | S2 | — | `user_id` — the gateway closes that user's sockets (4403) |
| `graph.delta` | S3 | — | `GraphDelta` (`app/graph/schemas.py`): `from_revision, to_revision, added, changed, removed, sentences` |

## 2. Publishing

`app.realtime.bus.publish(event)` — **after** the commit, never inside a transaction; it never raises. Redis pub/sub
channel per workspace: `rcd:events:<workspace_id>`. `REALTIME_BUS=memory` uses an in-process bus (tests, one process).

## 3. Socket protocol (`/ws`)

| Direction | Frame |
|---|---|
| client → | `{"type": "auth", "token": "<JWT>"}` — first frame, within 10 s, else close **4401** |
| ← server | `{"type": "ready", "user_id": "…"}` |
| client → | `{"type": "subscribe", "project_id": "…"}` or `{"type": "subscribe", "workspace_id": "…"}` |
| ← server | `{"type": "subscribed", …}` or `{"type": "error", "code": "not_found"}` (non-member = unknown id) |
| ← server | `{"type": "event", "event": {…envelope…}}` |
| client → / ← | `{"type": "ping"}` / `{"type": "pong"}` (every 25 s keeps proxies from idling the socket out) |

Membership is re-read on every `subscribe`, as on every REST request. A workspace subscription receives every event of
the workspace; a project subscription receives that project's events and workspace-level ones.

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
