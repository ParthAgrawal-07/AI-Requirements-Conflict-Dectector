# Final Accuracy and Regression Report — Sprint 6 (feature freeze)

| | |
|---|---|
| **Owner** | Abhyudit (QA — accuracy) · reviewers Heet (candidates, rules), Keval (classification, SRS prompts), Bansil (SRS fidelity), Dhavni (change log) |
| **Requirements** | NFR-21 (accuracy per category), NFR-37 (recall by layer), NFR-39 (context pack), DR-25 (SRS fidelity), FR-95 (written change log) |
| **Benchmark** | `eval/benchmark_v2`: planted SRS (60 requirements, 55 labels), post-style set (40 posts, 56 labels), reworded below-threshold set (24 pairs) |
| **Runs** | `eval/run_benchmark.py`, `eval/recall_by_layer.py` (embedder `all-MiniLM-L6-v2`, threshold 0.75, top-*k* 10) · results in `final_document_candidates.json`, `final_post_candidates.json`, `s6_layers.json` |

## 1. What was measured, and what was not

| Measure | Status |
|---|---|
| Extraction (document style) | ✅ 60 of 60, every printed ID kept (unchanged since CP1) |
| Candidate pre-filter, document and post style | ✅ §2 |
| Rule checks, reworded set and planted SRS | ✅ §3 |
| Classification precision / recall / F1 per category | ⬜ needs a live model run (§4) |
| Suggestion correctness study (NFR-36) | ⬜ needs a live model run (§4) |
| SRS fidelity on the planted baseline (DR-25) | ✅ §5 |
| Change-log sentences match the map deltas (FR-95) | ✅ §6 |
| Full regression | ✅ §7 |

As at CP1 and CP2, numbers that need the model are left empty rather than estimated: no API key is
configured on the build machine. Everything below is reproducible for free with the commands in §8.

## 2. Candidate pre-filter — the ceiling for the AI layer

| | Document style (A) | Post style (B) |
|---|---|---|
| Labelled pair issues | 20 | 37 |
| Became candidates | 10 (**50.0%**) | 18 (**48.6%**) |
| Conflicting | 2 / 8 | 10 / 17 |
| Duplicate | 6 / 6 | 8 / 12 |
| Dependent | 2 / 6 | 0 / 8 |

Unchanged from CP1 at the 0.75 threshold: duplicates pass the filter, conflicts and dependencies
worded differently mostly do not. This is the gap the rule checks (§3) and raised concerns (US-56)
exist for.

## 3. Recall by layer — rules (NFR-37)

| | CP2 | Final |
|---|---|---|
| Reworded set — rule-labelled conflicts caught | 12 / 12 | **16 / 16** |
| Reworded set — look-alike false positives | 0 / 3 | **0 / 5** |
| Reworded set — **held-out** conflicts caught | 4 / 5 | 4 / 5 |
| Planted SRS — conflicts caught by rules | 2 / 8 | **5 / 8** |
| Planted SRS — rule hits on non-conflicts (1,770 pairs) | 0 | **0** |

**Combined reach on the planted conflicts** (a candidate the AI is asked about, or a rule hit):
**5 of 8**, up from 2 of 8 at CP2 — the two candidate conflicts are also rule hits. The three
left (REQ-002/REQ-012, REQ-024/REQ-028, REQ-038/REQ-039) are semantic and below the threshold:
for the AI at a lower threshold, or a person. Heet's tuning used the dev split only
(`s6_rule_tuning.md`); the held-out number is reported, never tuned on.

## 4. Classification and suggestions — to run with a key

Recorded runs make every re-score free afterwards:

```bash
python eval/run_benchmark.py --llm live --context-pack on --clarify --record eval/reports/final_doc_pack.json
python eval/run_benchmark.py --style post --llm live --context-pack on --record eval/reports/final_post_pack.json
python eval/recall_by_layer.py --llm live --record eval/reports/final_ai.json
python eval/suggestion_rating.py   # the 30-suggestion correctness study (CP2 §4)
```

About 650 calls at the 0.75 threshold; one project's monthly budget covers it. Report the held-out
split separately (`--split heldout`).

## 5. SRS fidelity on the planted baseline (DR-25)

`backend/tests/integration/test_srs_fidelity.py` runs the whole updated-SRS path on the 60
approved planted requirements, with a Proposed requirement beside them:

| Check | Result |
|---|---|
| Readiness lists all 60 included requirements | ✅ |
| Fidelity passes on the accepted draft; 60 requirements checked | ✅ |
| Published v1.0: every requirement **exactly once and verbatim** in the Markdown export | ✅ 60 / 60 |
| … and in the DOCX export | ✅ 60 / 60 |
| The Proposed requirement's text and ID appear nowhere | ✅ |
| A narrative copying the Proposed text → `not_baseline`; a "must" without a baseline ID → `normative`; a requirement quoted twice → `duplicated` | ✅ all three caught |

Unit-level cases are in `tests/api/test_srs.py` (missing requirement, locked requirement sections,
immutability of a published version, v1.0 → v1.1 comparison, DOCX and PDF text).

## 6. Change-log sentences match the deltas (FR-95)

`backend/tests/integration/test_change_log.py`, on the planted SRS: a finding dismissed, a concern
raised (with its issue), a requirement protected and a link made — each through the API. For every
`graph.delta` with sentences, the change log holds exactly those sentences under the delta's
revision; kinds are `conflict_resolved`, `concern`, `issue`, `state`, `link`; the highlighted nodes
are the requirements touched; no sentence contains requirement text. A summary over three
dismissals counts `conflicts_resolved = 3`, equal to the dismissed conflicts in the database.

## 7. Regression

Full backend suite (ruff, ruff format, mypy, pytest with PostgreSQL 16 + pgvector and Redis 7),
run after each Sprint 6 backend commit:

| After | Passed |
|---|---|
| Dhavni (change log, time slider, timeline) | 3,068 |
| Madhav (discussion, votes, watch, links) | 3,329 |
| Keval (severity, AI feedback, summary paragraph, SRS prompts) | 3,404 + 1 fixed in a follow-up |
| Parth (compliance) | 3,459 |
| Bansil (updated SRS, exports, open items) | 3,650 |
| Heet (rule tuning) | 3,661 of 3,662 — the one failure, an ordering assumption in a compliance test, was fixed in a follow-up |
| Abhyudit (these integration tests) | 3,666 |

No test was skipped for want of a database. Tests marked `llm` (real API) are excluded by default,
as in CI.

## 8. Reproduce

```bash
python eval/run_benchmark.py --embedder minilm --llm none --json eval/reports/final_document_candidates.json
python eval/run_benchmark.py --style post --embedder minilm --llm none --json eval/reports/final_post_candidates.json
python eval/recall_by_layer.py --embedder minilm --llm none --json eval/reports/s6_layers.json
cd backend && pytest tests/integration/test_srs_fidelity.py tests/integration/test_change_log.py
```
