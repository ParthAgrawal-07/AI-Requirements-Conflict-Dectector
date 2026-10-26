# Spike — similar-requirement hint latency (Sprint 0)

| | |
|---|---|
| **Owner** | Heet |
| **Question** | Can the composer show "similar requirements" fast enough to run on every pause in typing? Target: under 500 ms server time (Detailed Sprint Guide, S0). |
| **Script** | `eval/latency/hints_bench.py` — embeds N synthetic requirements, then times *embed one text + pgvector top-5 in the project* per query; everything in one rolled-back transaction |

## Result (24 Oct 2026; updated 26 Oct 2026 with multi-tenant benchmark)

| Requirements in target project | Projects in DB | Queries | Median | p95 | Max | Embedding target reqs |
|---|---|---|---|---|---|---|
| 500 | 1 | 50 | **47 ms** | **151 ms** | 439 ms | 7.1 s |
| 500 | 5 (2,500 total) | 50 | **15 ms** | **18 ms** | 27 ms | 1.9 s |

Machine: developer laptop, Docker Desktop, worker container on CPU (8 cores, torch 2.14 CPU build),
all-MiniLM-L6-v2, PostgreSQL 16 + pgvector 0.8+ HNSW (m=16, ef_construction=64) using iterative scan
(`hnsw.iterative_scan = 'relaxed_order'` and raised `ef_search`) so post-filtered queries across
multiple projects retain full recall and stay well within latency budgets. Model loaded once beforehand.

**Conclusion:** well under 500 ms at p95 across both single-project and multi-tenant workloads.
