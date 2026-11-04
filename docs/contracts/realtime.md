# Real-time events — contract (Sprint 0–1)

| | |
|---|---|
| **Producer** | Dhavni didi (`app/realtime/`, `app/graph/schemas.py`) |
| **Consumers** | Pranshu (`app/socket.ts`, upload progress) · Abhijeet (live map) · Madhav (notifications, S5) · Affan (WebSocket tests) |
| **Stories** | US-03 (S1), US-29 (S2), US-14 (S3) |
| **Path** | `/ws` — WebSocket text frames carrying JSON |

## 1. Model

- **One connection per browser tab.** Components never open sockets; they register interest via
  `useProjectRealtime(projectId)`.
- **Events are hints.** Missed events are never replayed. On every `ready` frame (connect or reconnect) the client
  invalidates the relevant TanStack Query caches and re-syncs over REST — the REST API is the source of truth.
- **Polling fallback.** If realtime is unavailable or disabled (`VITE_REALTIME_ENABLED=false`), screens poll
  (e.g. `useDocuments` every 3 s while documents are active).

## 2. Envelope

```json
{"type": "analysis.progress", "workspace_id": "…", "project_id": "…", "channel_id": null,
 "entity_id": "…", "at": "2026-10-24T10:42:00Z", "data": {}}
```

`data` carries ids, states and numbers — never requirement or message text (CR-04). A client that needs text re-reads
it over REST, which also re-checks permissions.

| `type` | Since | `entity_id` | `data` |
|---|---|---|---|
| `analysis.progress` | S1 | document | `document_id, status (queued/processing/done/failed), progress_percent, stage, error_message` |
| `membership.revoked` | S2 | — | `user_id` — the gateway closes that user's sockets (4403) |
| `graph.delta` | S3 | — | `GraphDelta` (`app/graph/schemas.py`): `from_revision, to_revision, added, changed, removed, sentences` |

On `analysis.progress` with `status: "done"` the client invalidates `["documents", projectId]` and
`["requirements", projectId]`.

## 3. Socket protocol

| Direction | Frame |
|---|---|
| client → | `{"type": "auth", "token": "<JWT>"}` — first frame, within 10 s, else close **4401** |
| ← server | `{"type": "ready", "user_id": "…"}` |
| client → | `{"type": "subscribe", "project_id": "…"}` or `{"type": "subscribe", "workspace_id": "…"}` |
| ← server | `{"type": "subscribed", "workspace_id": "…", "project_id": "…"}` or `{"type": "error", "code": "…"}` |
| client → | `{"type": "unsubscribe", "project_id": "…"}` (or `workspace_id`) — no reply |
| ← server | `{"type": "event", "event": {…envelope…}}` |
| client → / ← | `{"type": "ping"}` / `{"type": "pong"}` — every 25 s, keeps proxies and NAT from idling the socket out |

The token travels in the first frame, not the URL, so it never lands in proxy logs. Membership is re-read on every
`subscribe`, as on every REST request. A workspace subscription receives every event of the workspace; a project
subscription receives that project's events and workspace-level ones.

Subscribe error codes: `not_found` (unknown id **or** not a member — deliberately the same answer), `forbidden`
(member without `view`), `scope_required` (neither id given), `unavailable` (event bus down; retry later or poll).

### Close codes

| Code | Meaning | Client |
|---|---|---|
| 4401 | No valid `auth` frame (invalid/expired token, timeout) | Clear auth state, prompt sign-in, do not reconnect |
| 4403 | Membership revoked | Invalidate workspace and permission caches, do not reconnect |

### Reconnection (client)

On any other disconnect: exponential backoff, `delay = min(30000, 1000 * 2^attempts)`; after 5 consecutive failures
stop retrying and fall back to REST polling.

## 4. Publishing (backend)

`app.realtime.bus.publish(event)` — **after** the commit, never inside a transaction; it never raises. Redis pub/sub,
one channel per workspace: `rcd:events:<workspace_id>`. `REALTIME_BUS=memory` uses an in-process bus (tests, one
process).

## 5. Progress stages (US-03)

| Stage | `status` | `progress_percent` |
|---|---|---|
| uploaded | `queued` | 0 |
| claimed by the worker, extracting | `processing` (`stage: extraction`) | 10 |
| text extracted, saving | `processing` (`stage: persistence`) | 60 |
| finished | `done` (`stage: null`) | 100 |
| failed | `failed` (`stage` = where, `error_message` = `[stage] reason`) | 0 |

## 6. Queues

`documents.*` → `documents`; `embeddings.*`, `classification.*`, `analysis.*` → `analysis`; everything else →
`celery`. Compose runs one worker on all three and one `beat` (periodic jobs: join-code expiry; later the budget reset).
