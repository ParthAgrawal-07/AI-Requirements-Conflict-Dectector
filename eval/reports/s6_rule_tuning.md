# Sprint 6 — rule-check recall tuning (US-58, NFR-37)

| | |
|---|---|
| **Owner** | Heet (rule checks) · reviewers Keval (attributes), Abhyudit (accuracy) |
| **Code** | `backend/app/search/rule_checker.py` (`unbounded` rule, `with_frequencies`, `read_attributes`) |
| **Data** | `eval/benchmark_v2/below_threshold.csv` (+6 dev rows, BT-19 to BT-24) · results `eval/reports/s6_layers.json` |
| **Run** | `python eval/recall_by_layer.py --embedder minilm --llm none --json eval/reports/s6_layers.json` |

## What changed, and why

The CP2 report listed what the rules missed. On the **dev** split, two classes could be handled by
rule without guessing at meaning:

1. **A limit against no limit.** "Admin sessions shall expire after 5 minutes" and "Sessions shall
   remain active until the user explicitly logs out" (planted REQ-004/REQ-032, REQ-020/REQ-032);
   "at most 3 concurrent sessions per user" and "any number of devices at the same time"
   (REQ-036/REQ-037). New rule **`unbounded`**: a finite limit in one requirement and an explicit
   "no limit" for the same measure in the other ("until … logs out", "never expires", "kept
   indefinitely", "never deleted", "any number of … at the same time"). The open side is indexed
   under the measure it leaves open, so the two are compared at all; subjects match by the usual
   subject test or by a shared noun (session, user, record…).
2. **Frequency words.** "refreshed hourly" is read as "every 1 hour" (also nightly, daily, weekly,
   monthly, yearly, "every day"), so two refresh periods can be compared by the existing
   `numeric_limit` rule.

`eval/recall_by_layer.py` now reads attributes through `read_attributes`, the same function the
checker indexes with, so the evaluation cannot drift from the product.

Not attempted (semantic, for the AI or a person): data residency vs offshore backups (BT-13),
guest checkout vs registered customers (BT-14), encryption vs plaintext, hashing vs viewing
passwords, anonymised vs named.

## Results (rules only, no LLM)

| Set | CP2 | Sprint 6 |
|---|---|---|
| Reworded set — rule-labelled conflicts caught | 12 / 12 | **16 / 16** (4 new dev rows) |
| Reworded set — look-alike false positives | 0 / 3 | **0 / 5** (2 new dev look-alikes) |
| … dev conflicts caught | 8 / 10 | 12 / 14 |
| … **held-out** conflicts caught (never tuned on) | 4 / 5 | 4 / 5 — BT-15 still missed |
| Planted SRS — labelled conflicts caught by rules | 2 / 8 | **5 / 8** |
| Planted SRS — rule hits on unlabelled pairs or labelled non-conflicts | 0 | **0** |

The planted pairs the new rule catches are dev pairs; the labelled non-conflicts next to them
(REQ-036/REQ-004, REQ-037/REQ-032) stay quiet and are asserted in
`backend/tests/search/test_rule_tuning.py`. Held-out BT-15 ("generated nightly" vs "figures at most
one hour old") needs a freshness rule across two subjects; it was deliberately not tuned for, and
Abhyudit reports it as missed.

## Candidate generation

`app/embeddings/candidates.py` is unchanged: the misses above are all below the similarity
threshold, which is exactly the gap the rules exist for (ADR-30). Lowering the threshold would send
more pairs to the AI at a cost the budget triggers forbid (Sprint Plan §8).
