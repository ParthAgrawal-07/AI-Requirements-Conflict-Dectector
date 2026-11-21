# Checkpoint 2 Load Test — messages, live analysis, checks, live map at 500 requirements

| | |
|---|---|
| **Owner** | Dhavni (with Affan) · reviewers Heet (rule checks), Madhav (realtime) |
| **Requirements** | NFR-24 (messages), NFR-25 (result card), NFR-26 (consequence report), NFR-32 (live map), NFR-33 (500-node map) |
| **Scripts** | `load/messages.js`, `load/analysis.js`, `load/checks.js`, `load/map.js`, shared set-up in `load/lib.js` (k6 0.54) |
| **Date** | Sprint 5, Checkpoint 2 |

## 1. The stack it ran on

One laptop: Intel Core i5-1135G7, 8 GB RAM; Docker with 8 CPUs and 3.9 GB. API: `uvicorn` with 2 workers; one
Celery worker (concurrency 4) on every queue; PostgreSQL 16 + pgvector; Redis 7. k6 ran in Docker on the same host,
so event lags are measured on one clock (see `load/lib.js`).

**Rules-only: no model key.** Analysis, checks and the map ran without any LLM call: embeddings, candidate pairs, rule
checks, consequence checks and graph deltas are all real; the AI classification, the AI narrative of a consequence
report and AI suggestions are absent. §5 says why the 500-requirement runs cannot pass with a model key on the default
budget either.

**The load project.** `lib.js` fills a project to **500 requirements in 50 subjects of 10** ("The billing service
shall respond within 1..10 seconds"), posted by seven members at 25 a minute each (posts are rate-limited per member,
US-29). Every pair inside a subject breaks the numeric-limit rule, so the rule checks give **2,250 edges** — above
NFR-33's 2,000. The project's similarity threshold is 0.95, so no pair waits for a model.

## 2. Results

Final code (after the three fixes in §3), fresh database, one run each.

| NFR | Load | Target | Measured | |
|---|---|---|---|---|
| NFR-24 messages | 50 members on #general, 7 senders, one message each per 4 s, 2 min | p95 < 1 s to every member | **p95 28 ms** (max 56 ms) from publish to each of 12,600 deliveries; sender's round trip incl. the POST p95 93 ms; 0 lost, 0 errors | ✅ |
| NFR-25 result card | 500 requirements; 20 members, 7 posting every 10 s, 3 min | 90% within 60 s | **p90 1.6 s** (max 2.5 s) from before the POST to `analysis.completed`; 0 lost — rules-only | ✅ |
| NFR-26 consequence report | 500 requirements; 7 proposers, a change request every 15 s each, 3 min | 90% within 90 s | **p90 0.96 s** (max 2.3 s) from before the POST to `change_request.checked`; 0 lost — no AI narrative | ✅ |
| NFR-32 live map | 50 open maps of the 500-node project, 7 posting a requirement every 15 s, 3 min | p95 < 2 s | **p95 34 ms** from publish to every open map; poster's own map from before the POST p95 288 ms; 0 lost | ✅ |
| NFR-33 map size, in the browser | 500 nodes, 2,250 edges; production build, headless Chromium 1440×900; pan and zoom for ~8 s; 3 runs | no frame > 100 ms | **0 frames over 100 ms** in 1,031; max 50 ms, p95 17 ms; map drawn 2.5–3.1 s after sign-in | ✅ |
| Snapshot when 50 maps open at once | the same 50 viewers, each `GET /graph` once at start | NFR-02: 2 s | **p95 16.0 s** (0.4 s for the first, alone); no errors | ❌ |
| Stress: every map reloads every 30 s | as NFR-32, plus a full snapshot per viewer every 30 s (a reconnect storm) | NFR-32 | delta **p95 3.7 s**, 4 lost; snapshot p95 19.4 s; no errors | ❌ |

**What does not pass: the 500-requirement snapshot under concurrency.** One `GET /projects/{p}/graph` at 500 nodes and
2,250 edges takes about 0.4 s; fifty at once queue behind the two API workers and the 15 pooled connections each, so
the last viewer waits 16 s for the first paint. Deltas are unaffected in normal use (the map page loads the snapshot
once and then applies deltas, `features/map/useGraphDeltas.ts`), but when every browser reconnects together the
snapshot load crowds out delta delivery. The Sprint 0–5 code review cut the snapshot's cost about sevenfold (§7);
what remains for Sprint 6 (Dhavni): cache the serialised snapshot per `revision` (one build per revision, not per
viewer) once every map-visible write is confirmed to bump the revision, and let a reconnecting client send
`?revision=` so an unchanged map answers 304.

## 3. Defects the load test found, and fixed

| # | Found | Cause | Fix (in this sprint) | Before → after |
|---|---|---|---|---|
| 1 | Posts a moment apart: a worker task died with `UniqueViolation` | `generate_candidates` read the pairs, then inserted; two runs both inserted the same pair | `ON CONFLICT DO NOTHING`, reuse the other run's row (`app/embeddings/candidates.py`, Heet's zip) | the run's rule checks never ran → every run completes |
| 2 | 2,249 of 2,250 rule edges on the load project | the same race inside the rule checks (`rule_checker._pair`) rolled back **every finding of that run** | same fix (`app/search/rule_checker.py`, Heet's zip) | one conflict silently never flagged → 2,250 of 2,250 |
| 3 | 4 of 22 messages failed with HTTP 500 when 50 members connected | each open socket held its session's transaction — and so a pooled connection — until it closed; 50 sockets ran the pool dry (`QueuePool limit of size 5 overflow 10 reached`) | the gateway ends the transaction after signing in and after each subscription (`app/realtime/gateway.py`, this zip) | NFR-24: 4 errors, 4 lost → 0 and 0; stress run: 500s and delta p95 36 s → no errors, p95 3.7 s |

Each fix has a test that fails without it: `test_two_runs_at_once_share_one_pair`,
`test_two_runs_checking_one_pair_at_once_share_it` (two real connections), `test_an_open_socket_holds_no_database_connection`.

## 4. Not measured

| Item | Why |
|---|---|
| AI latency inside NFR-25 and NFR-26 (classification, narrative) | no model key on the test stack (as for Abhyudit's CP2 recall report) |
| NFR-34 (lint within 300 ms) | lint runs in the browser on the same catalogue; covered by the composer tests, not a load property |
| A remote client (network latency) | k6, the API and the browser shared one host; on staging pass `-e API_URL=` |

## 5. With a model key, the 500-requirement runs do not pass either

Every new requirement costs at least one LLM call (its single checks) plus one per candidate pair, and the platform
default is **200 calls a month** (`LLM_PLATFORM_MONTHLY_CALLS`, under the project's own 2,000). Filling the load project
uses the month's budget after about 200 posts; every later run parks in `waiting_budget`, so the result cards wait, the
requirements cannot be approved (approval needs analysis on the current text) and the map's edges come from rules only.
NFR-25 excludes budget waits, and `analysis.js` counts them apart (`analysis_waiting_budget`), but the numbers would
describe a parked queue, not the AI. A load run with a model needs `LLM_BUDGET_BACKEND=unlimited` on a throw-away stack
and a provider quota of several thousand calls for one seeding (500 single checks plus up to `CANDIDATE_TOP_K`
pair classifications each); free-tier keys also rate-limit far below the posting rate
used here.

## 6. Reproduce

```sh
docker compose up -d && docker compose exec backend python -m app.cli seed-demo
k6 run load/map.js           # seeds "Load test (500)" on first use (~5 min), then 50 open maps for 3 min
k6 run load/analysis.js      # NFR-25
k6 run load/checks.js        # NFR-26
k6 run load/messages.js      # NFR-24, on the demo project's #general
k6 run -e RELOAD_EVERY_S=30 load/map.js   # the reconnect-storm stress case
```

NFR-33 in the browser: open the load project's map in a production build (`npm run build && npm run preview`), record
a Performance profile while panning and zooming, and look for frames over 100 ms.

## 7. After the Sprint 0–5 code review (`Review.zip`)

Profiling one snapshot of the 500-node map: the edges were built from 2,250 whole findings (with their stored model
output) through two outer joins and an `OR`, and FastAPI validated the finished snapshot a second time. The review
reads only the columns an edge shows, filters on the finding's own `project_id`, and serialises once.

| | Before | After |
|---|---|---|
| One snapshot, 500 nodes / 2,250 edges: edges · encoding (profiled alone) | 375–450 ms · 80–110 ms | **45–60 ms · 6 ms** |
| Rule checks of a 200-requirement document (profiled alone) | 62.0 s | **22.7 s** (partial indexes now used, below) |
| 50 maps opening at once: snapshot p95 | 16.0 s | 6.2–6.7 s (still above 2 s: the per-revision cache in §2) |
| Reconnect storm: delta p95 · lost | 3.7 s · 4 | **0.39–0.64 s · 0** (NFR-32 holds) |
| Reconnect storm: snapshot p95 | 19.4 s | 5.6–13.1 s |

The k6 "after" figures are two runs, and in both the laptop was also doing other work (a profiling job in one,
starting and seeding a local demo stack in the other), so read them as upper bounds; re-run `k6 run load/map.js`
on an otherwise idle machine for a clean figure. The profiled rows were measured alone, before and after.

The rule checks spent most of their time asking whether a pair's rule finding already existed: the query said
`is_stale IS FALSE`, which PostgreSQL cannot match to the partial unique index (`WHERE NOT is_stale`), so every check
scanned the whole findings table. All such filters now say `NOT is_stale`.

Same stack and scripts as §1; map runs on a fresh database, 3 minutes each.
