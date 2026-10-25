# Spike — similar-requirement hint latency (Sprint 0)

| | |
|---|---|
| **Owner** | Heet |
| **Question** | Can the composer show "similar requirements" fast enough to run on every pause in typing? Target: under 500 ms server time (Detailed Sprint Guide, S0). |
| **Script** | `eval/latency/hints_bench.py` — embeds N synthetic requirements, then times *embed one text + pgvector top-5 in the project* per query; everything in one rolled-back transaction |

## Result (24 Oct 2026)

| Requirements in the project | Queries | Median | p95 | Max | Embedding the 500 |
|---|---|---|---|---|---|
| 500 | 50 | **47 ms** | **151 ms** | 439 ms | 7.1 s |

Machine: developer laptop, Docker Desktop, worker container on CPU (8 cores, torch 2.14 CPU build),
all-MiniLM-L6-v2, PostgreSQL 16 + pgvector HNSW (m=16, ef_construction=64). Model loaded once beforehand (a worker
loads it once at start-up, not per request).

**Conclusion:** well under 500 ms at p95. The single slow query (439 ms) is the first one after warm-up; run the
script on the deployment machine before CP1 and add a row here.
