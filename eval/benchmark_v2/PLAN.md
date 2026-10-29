# Benchmark v2 Plan

| | |
|---|---|
| **Owner** | Abhyudit (QA: accuracy and backend) |
| **Reviewers** | Keval (classification), Heet (embeddings and retrieval) |
| **Status** | Draft for review (Sprint 0) |
| **Seed material** | `sample_docs/planted_conflicts/` (labeling guide, `srs_v1.md`, `srs_v1_labels.json`) |
| **Schema** | `schema.json` in this folder |

All numbers below are **proposed targets**. Reviewers may change them; the plan is accepted when Keval and Heet approve it.

## 1. Purpose

The classifier is an LLM, so "it works" needs evidence. The benchmark gives the team a labeled, repeatable way to measure:

- how well the five-category classifier performs (US-05, US-07),
- whether the embedding pre-filter drops real issues (candidate recall),
- whether the impact engine finds the right affected requirements and owners (US-11, US-34),
- how much the rule checks (US-58) add on conflicts the AI misses.

## 2. Components

| ID | Component | Style | Size (target) | Used for |
|---|---|---|---|---|
| A | Planted-conflict SRS (`srs_planted.docx`, grown from `srs_v1`) | Document | about 60 requirements with printed IDs (`REQ-001` ...) | Extraction count (US-02), classifier accuracy (US-05) |
| B | Post-style requirements | Short composer/EARS style | 40 requirements, each with an author/owner | Live analysis (US-31), post-style accuracy at CP1 |
| C | Scripted change requests | Change-request text | 10, each with expected affected set and owners | Impact analysis and findings delta (US-11, US-34) |
| D | Reworded conflicts | Either | at least 12 conflicting pairs worded to share little vocabulary | Pre-filter recall, rule-check value (US-58, CP2) |

### Planted issues in A (proposed)

| Category | Pairs / items | Notes |
|---|---|---|
| Conflicting | 8 | Include quantitative ones (e.g. different retention periods, limits) |
| Duplicate | 6 | Paraphrases, some with different detail |
| Ambiguous | 8 | Single-requirement items: vague terms, unbounded phrases |
| Incomplete | 6 | Single-requirement items: missing actor, condition, or error handling |
| Dependent | 6 | One requirement relies on another |
| **None** (hard negatives) | at least 20 | Look-alike pairs that are NOT issues; needed to measure precision |

Also include some **noise** in the document that extraction must not turn into requirements: headings, intro prose, tables, informational sentences without "shall". The expected count is the number of REQ-nnn identifiers in srs_planted.md; the upload test derives it from there (5% tolerance, US-02).

### Component B (post-style)

- Short statements in the composer's EARS templates (ubiquitous, event, state, unwanted, optional).
- Written as if posted by different owners, against the baseline in A.
- Mix: roughly a quarter clean, the rest with a planted issue against A or against another post.

### Component C (change requests)

- 10 requests covering: no impact, single-requirement impact, multi-owner conflict, a dependency break, a duplicate being introduced, and a request touching a protected requirement.
- Each lists `expected_affected_ids`, `expected_owners`, and any `expected_new_conflicts`.

### Component D (reworded conflicts)

- Conflicting pairs with different vocabulary and structure, so cosine similarity may fall below the threshold.
- Flagged `reworded: true` in the labels. Used at CP2 to split recall into caught by AI, caught by rules, and missed.

## 3. Labeling process

1. Follow `LABELING_GUIDE.md` (definitions, examples, edge cases). Update it if v2 adds cases.
   - **Label format** (same as `srs_v1_labels.json`): `r1`, `r2` (pairwise only), `category` (`Conflicting`, `Duplicate`, `Ambiguous`, `Incomplete`, `Dependent`, `None`; capitalized, matching `FindingCategory`), `note`. v2 adds optional `source`, `reworded`, `split`, `annotators`.
   - `None` is the hard-negative category. Single-requirement categories (Ambiguous, Incomplete) have no `r2`.
   - v1 stays as JSON and is never edited after a benchmark run. v2 labels are kept in `labels.csv` (easier for two people to label independently and diff), with the same column names; the harness loads both.
2. Two people label independently; disagreements are reconciled and the final label recorded.
3. Record annotators in each row; report agreement (Cohen's kappa) for the first full pass.
4. Keval or Heet reviews a sample of labels before the benchmark is declared ready.
5. Every issue is labeled **per requirement or pair using the printed IDs**, never by line number.

### v1 review decisions (applied in a separate PR)

- **Refinement rule:** the labeling guide now has a coverage test. Duplicate means each requirement covers everything the other requires; Dependent means a functional dependency; subsumption (one restates the other and adds detail) is None.
- **Rewordings so labels hold:** REQ-014, REQ-017, REQ-019, REQ-024, REQ-029. New requirements REQ-032 and REQ-033 add two conflicts and a look-alike hard negative.
- **Labels:** REQ-022 added as Incomplete; two trivial None pairs replaced with look-alike pairs. v1 now has 33 requirements and 24 labels.
- **Unlabeled items:** findings on items without a label are adjudicated; precision is reported both strict and adjudicated.
- **v1 is the seed and dev set.** The 70/30 split starts with v2. The second labeler labels the revised `srs_v1.md` blind (without the labels).
- **v1 is flat by design** (one requirement per line). The v2 SRS adds headings and prose, as real documents do, to test extraction.

## 4. Dev and held-out split

- 70% dev, 30% held-out.
- Split by **issue cluster**, so a requirement and its look-alikes never straddle the split.
- Developers tune prompts and thresholds on dev only. Abhyudit reports on held-out.

## 5. Metrics

- **Per category:** precision, recall, F1 (`sklearn.metrics.classification_report`).
- **Style:** document-style (A) and post-style (B) reported separately.
- **Context pack:** with and without, at CP1.
- **Candidate recall:** of truly problematic pairs, the share that survives the pre-filter (reported to Heet).
- **Recall by layer (CP2):** caught by AI, caught by rules, missed.
- **Impact (C):** precision and recall of affected sets; exact match on owners.
- **Unlabeled findings:** adjudicated per the labeling guide; report strict and adjudicated precision.
- **Report format:** a Markdown report in `eval/reports/` per checkpoint.

## 6. Files and layout

```
eval/
  benchmark_v2/
    PLAN.md                 (this file)
    schema.json             record formats for labels and change requests
    LABELING_GUIDE.md       (carried over / extended in Sprint 1)
    srs_planted.docx        (Sprint 1)
    labels.csv              (Sprint 1; validated against schema.json)
    change_requests.json    (scripted change requests)
  reports/                  (accuracy and recall reports per sprint)
  run_benchmark.py          (Sprint 2)
```

`sample_docs/planted_conflicts/` stays in place until the fixtures that point at it are updated.

## 7. Schedule

| Sprint | Work |
|---|---|
| S0 | This plan and `schema.json`, reviewed by Keval and Heet |
| S1 | `srs_planted.docx`, `labels.csv`, upload and extraction API tests |
| S2 | First accuracy run (`run_benchmark.py`, `reports/s2.md`) |
| S3 | CP1 report, document vs post style, with and without context pack |
| S4 | Affected sets and auto-issue owners for the scripted change requests |
| S5 | CP2 recall report including reworded conflicts; suggestion correctness study |
| S6-S7 | Regression, final accuracy, demo data |

## 8. Hand-offs

- **Bansil:** exact expected requirement count and the SRS file early in Sprint 1.
- **Keval:** label format maps to the classifier's output schema; please confirm field names.
- **Heet:** candidate-recall metric definition; the reworded set (D) for threshold tuning.
- **Affan:** the SRS file for the E2E upload test.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Labels disagree or drift | Labeling guide, two labelers, reconciliation, recorded agreement |
| Benchmark too small to be meaningful | Report counts with every metric; extend in S2 if categories have too few items |
| Developers overfit to dev set | Held-out set reported only by QA |
| Fictional domain not representative | Add a second domain in S2-S3 if time permits |

## 10. Review checklist (for Keval and Heet)

- [ ] Categories and definitions match how the classifier will be prompted
- [ ] Label fields map cleanly onto the output schema
- [ ] Reworded set is hard enough to test the pre-filter
- [ ] Metrics are the ones the team will track at CP1 and CP2
- [ ] Split rule is acceptable
- [ ] Refinement rule (Dependent vs None) agreed and written into the labeling guide
