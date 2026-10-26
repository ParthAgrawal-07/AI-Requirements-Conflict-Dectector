# Conflict Detection Strategy — not losing conflicts to the similarity filter

| | |
|---|---|
| **Status** | Proposed (ADR-30). Nothing in this document is implemented yet; it is the build plan for Sprint 2 (US-05) and Sprint 5 (US-58) |
| **Owners** | Heet (candidate generation, rule checks) · Keval (attribute extraction, prompts) · Abhyudit (measurement) · Parth (orchestration, migration review) |
| **Builds on** | ADR-01 (embedding pre-filter), ADR-27 (rule-based cross-checks), ADR-28 (context pack), DR-10, NFR-05, NFR-37 |
| **Benchmark** | `eval/benchmark_v2/srs_planted.md` + `labels.csv` (60 requirements, 8 Conflicting pairs of which 3 are reworded, 21 hard negatives) |

## 1. The problem

The detection engine sends a pair of requirements to the LLM only if the embedding pre-filter picks it (ADR-01). **A pair
that never becomes a candidate can never become a finding** — no prompt, model or reviewer will ever see it. So the
recall of the whole system is capped by the recall of the candidate step.

Vector similarity is a poor judge of conflict, and it fails in both directions:

| Pair (planted SRS) | Similarity | Conflict? | Why similarity misleads |
|---|---|---|---|
| REQ-021 "API requests shall time out after 2 seconds" / REQ-023 "… permitted up to 10 seconds" | high | **yes** | the clash is one number; the sentences look alike — similarity happens to work |
| REQ-004 "Admin sessions expire after 5 min" / REQ-020 "Guest sessions expire after 5 min" | high | no | different subject; similarity over-selects (acceptable: the LLM says None) |
| REQ-028 "passwords hashed using bcrypt" / REQ-024 "administrators view stored passwords in plaintext" | **low** | **yes** | the contradiction is in meaning (hashed ⇒ unreadable), not in shared words |
| REQ-036 "at most 3 concurrent sessions per user" / REQ-037 "stay signed in on any number of devices at the same time" | **low** | **yes** | synonyms (session ↔ signed in, concurrent ↔ at the same time) and a bound vs "any number" |
| REQ-038 "exported reports shall contain only anonymised data" / REQ-039 "each exported report shall list the full name and email address of every user" | medium-low | **yes** | anonymised ⇔ names and e-mails is world knowledge |

Over-selecting costs LLM calls; under-selecting loses conflicts silently. The strategy below accepts a bounded amount of
the first to eliminate the second.

## 2. Principles

1. **Recall first at the candidate step; precision comes from the classifier and from people.** A wrong candidate costs
   one LLM call; a missed candidate costs a defect in the agreed baseline.
2. **Any one signal is enough to make a pair a candidate.** Signals are combined with OR, then ranked; no signal can veto.
3. **Deterministic and explainable.** Every candidate records *why* it was chosen (its signals), so a reviewer and the
   benchmark report can see which layer found what.
4. **Similarity stays a filter, never proof** (DR-10). Rule signals are also hints, not verdicts, until US-58 turns the
   strongest of them into findings with `source = rule` (ADR-25, ADR-27).
5. **Budget-bounded.** A per-requirement cap and a per-run cap keep the LLM spend predictable (NFR-38).
6. **Measured.** Candidate recall is reported per category, per signal, and separately for reworded pairs, from Sprint 2
   on — not only at CP2.

## 3. The pipeline

```
requirement text
   │
   ├─ 0. normalise ─────────── strip printed ID prefix, lower-case, number words → digits, light stemming
   ├─ 1. extract attributes ── quantities+units+bounds, modality/negation, concepts, actor, content terms   (no LLM)
   │
   ├─ 2. candidate generation (OR of signals, then rank and cap)
   │      S1 embedding neighbours      S2 shared rare terms      S3 quantity clash
   │      S4 opposed concepts          S5 bounded vs unbounded   S6 opposite modality
   │
   ├─ 3. LLM classification ─── pair prompt + context pack + "pre-check notes" from step 2
   │
   ├─ 4. rule cross-checks ──── strongest deterministic clashes become findings, source = rule   (US-58, S5)
   │
   └─ 5. people ─────────────── review (US-10), raise a concern (US-56 → records ai_miss)
```

| Step | Sprint | Owner | Where |
|---|---|---|---|
| 0–1 minimal extractor (quantities, modality, concepts, terms) | **S2** (pulled forward from S5) | Keval | `app/classification/attributes.py`, lexicon `app/classification/concepts.yaml` |
| 2 hybrid candidate generator | **S2** | Heet | `app/embeddings/candidates.py` |
| 3 pre-check notes in the pair prompt | **S2** | Keval | `prompts/pair_v1_*.md` (→ `pair_v2_*` once v1 has a benchmark run), `prompting.py` |
| candidate-recall evaluation | **S2** | Abhyudit (with Heet) | `eval/candidate_recall.py`, `eval/reports/s2.md` |
| 1 full extractor (actor, condition, entity/metric index) | S5 | Keval | `AttributeExtractor`, table `requirement_attributes` (0010b) |
| 4 rule checks as findings | S5 | Heet | `app/search/rule_checker.py` |
| 5 human layer | S3–S4 | Parth (US-10), Bansil (US-56) | as planned |

## 4. Step 0–1 — normalisation and attribute extraction (minimal, Sprint 2)

Pattern-based, no LLM, a few milliseconds per requirement. It runs on every requirement once (after extraction) and is
cached in memory per run in Sprint 2; Sprint 5 persists it in `requirement_attributes`.

**Normalisation**

* Remove the printed ID prefix (`REQ-014:`), so ID digits are never read as quantities.
* Lower-case; map number words to digits (`one`…`twenty`, `a dozen`); keep the original text for display.
* Light stemming (strip `-s`, `-es`, `-ed`, `-ing`, `-ion`, `-ly`) for term matching only.

**Attributes**

| Attribute | Example | Notes |
|---|---|---|
| `quantities[]` = (value, unit, dimension, bound) | "after 5 minutes" → (300, s, time, eq); "up to 10 seconds" → (10, s, time, max); "at most 3 sessions" → (3, count, count, max); "25 MB" → (26 214 400, B, size, max) | dimensions: time, size, percent, count, money, rate. Bound words: *at most, up to, no more than, within, maximum, limit of* → max; *at least, minimum, no less than* → min; otherwise eq |
| `unbounded` | "any number of devices", "unlimited", "no limit", "as many as needed" | flag; pairs with a `max` bound on the same concept (S5 signal) |
| `modality` | shall / must → mandatory; shall not / must not / never / may not → prohibited; may / can / should → optional | per clause |
| `concepts[]` | "signed in", "logged in", "session" → `session`; "hashed", "encrypted", "bcrypt", "AES" → `protected_secret` | from the concept lexicon below |
| `terms` | content stems minus stop words | used for S2 and as the "shared subject" test |
| `actor` (S5) | "Administrators", "the system", "Guest sessions" | first noun phrase before the modal verb |

**Concept lexicon** — a small, reviewed YAML file (`app/classification/concepts.yaml`), not code. Each concept lists
phrases; `opposes:` lists the concepts it contradicts. Starting set (extend from the dev split only — see §9):

| Concept | Phrases (examples) | Opposes |
|---|---|---|
| `session` | session, signed in, logged in, stay signed in | — |
| `concurrency` | concurrent, simultaneous, at the same time, in parallel, multiple devices | — |
| `expire` | expire, time out, end the session, log out, sign out | `persist` |
| `persist` | remain active, stay active, until … logs out, never expire | `expire` |
| `protected_secret` | encrypted, hashed, bcrypt, AES, encrypted at rest | `plaintext` |
| `plaintext` | plaintext, plain text, clear text, unencrypted, readable | `protected_secret` |
| `anonymous` | anonymised, anonymized, pseudonymised, de-identified, aggregated only | `personal_data` |
| `personal_data` | full name, name, e-mail address, phone number, home address, personal data | `anonymous` |
| `retain` | retain, retention, keep for, archive for, preserve | `delete` |
| `delete` | delete, purge, erase, remove permanently, destroy | `retain` |
| `allow` | allow, permit, be able to, may | `forbid` |
| `forbid` | shall not, must not, never, prohibit, forbid, block | `allow` |

## 5. Step 2 — hybrid candidate generation (Sprint 2)

A pair (A, B) in the same project becomes a candidate when **at least one** signal fires. "Shared subject" below means:
at least two shared content stems, or one shared stem with high IDF in the project, or a shared concept.

| Signal | Fires when | Default | Catches (planted SRS, expected) |
|---|---|---|---|
| **S1 Embedding neighbours** | B is among A's top-*k* by cosine **or** cosine ≥ threshold | k = 10, threshold = project `similarity_threshold` (0.75 was tuned for MiniLM — re-tune for bge-small-en-v1.5, ADR-31) | REQ-021/023, REQ-004/032, REQ-020/032, and most duplicates |
| **S2 Shared rare terms** | IDF-weighted overlap of content stems ≥ θ (BM25-style, or PostgreSQL full-text search) | θ tuned on dev so S2 alone adds ≤ 3 pairs per requirement | REQ-034/035 ("audit log entries"), REQ-038/039 ("exported report") |
| **S3 Quantity clash** | both have a quantity of the same dimension, values or bounds incompatible, shared subject | — | REQ-021/023 (2 s vs 10 s), REQ-034/035 (7 years vs 12 months) |
| **S4 Opposed concepts** | A has concept X, B has a concept that `opposes` X, shared subject | lexicon | REQ-002/012, REQ-028/024, REQ-004/032, REQ-020/032, REQ-034/035, REQ-038/039 |
| **S5 Bounded vs unbounded** | A has a `max` bound on a concept, B is `unbounded` on the same or a related concept | — | REQ-036/037 |
| **S6 Opposite modality** | same action/object stems, one mandatory/allowed and the other prohibited | — | "users shall export …" vs "users shall not export …" (add to benchmark v2.1) |

**Ranking and caps.** Each signal has a weight (start: S3 = S4 = S5 = S6 = 3, S1 = 2 × cosine, S2 = 1 × normalised
overlap); a pair's score is the sum. Keep, per requirement, the top `max_candidates_per_requirement` (default 8) and, per
run, the top `max_candidates_per_run` (default: what the remaining LLM budget allows). Pairs with any rule signal
(S3–S6) are never cut by the per-requirement cap — they are the cheapest to verify and the most likely to be real.

**What is stored.** `candidate_pairs` keeps the cosine in `similarity_score` for every candidate (computed even when S1
did not fire) and, with migration `0006` (Sprint 2, Parth reviews), gains `signals jsonb` (e.g.
`["S1", "S4:protected_secret/plaintext"]`) next to the planned `classification_status`. The signals feed the report,
the pre-check notes and later the map tooltip.

**Incremental mode** (US-31, Sprint 3) uses the same function with one new requirement against the project's baseline;
S1 uses pgvector top-*k*, S2–S6 use the in-memory or stored attributes. Nothing else changes.

**Interface** (for Heet and the orchestrator):

```python
@dataclass(frozen=True)
class Candidate:
    a_id: uuid.UUID
    b_id: uuid.UUID          # canonical order (a < b), as CandidatePair.ordered
    cosine: float
    score: float
    signals: tuple[str, ...]  # e.g. ("S1", "S3:time 2s/10s")
    notes: tuple[str, ...]    # human-readable pre-check notes for the prompt

def find_candidates(items: Sequence[Item], config: CandidateConfig) -> list[Candidate]: ...   # pure, testable
def generate_for_project(db, project, embedder) -> list[Candidate]: ...                       # loads, calls, persists
```

## 6. Step 3 — pre-check notes in the LLM prompt (Sprint 2)

The pair prompt gains an optional block after the context pack, built only from S3–S6 signals:

```
<pre_checks>
Automated pattern checks (they can be wrong, for example when the two requirements are about different subjects):
- Both state a time limit: REQ-021 says 2 seconds, REQ-023 says up to 10 seconds.
- REQ-028 says passwords are hashed; REQ-024 says they are viewed in plaintext.
</pre_checks>
```

Rules for this block: facts only (quoted values, which concept), never a suggested category; escaped like requirement text;
the system prompt states it is data to verify, not an instruction. The CP1 report measures accuracy **with and without**
pre-check notes, as it does for the context pack (NFR-39), so the team can see whether the hints help or bias the model.

**Disagreements are kept.** When a pair has a rule signal and the LLM answers None with confidence below 0.7, store the
pair with `classification_status = disputed` (0006). Sprint 2 counts them in the report; from Sprint 5, US-58 turns
the deterministic subset (S3 quantity clashes on the same metric, S6 opposite modality) into findings with
`source = rule` that stay visible even when the LLM disagrees (test-plan US-58 case).

## 7. Step 4–5 — rule findings and people (Sprint 5, Sprint 3–4)

Unchanged from ADR-25/27: US-58 adds `requirement_attributes` (indexed by entity and metric) and `RuleChecker` producing
findings with `rule_id`; US-56 lets anyone raise a concern, recorded as `ai_miss` when no AI or rule finding covered it.
This document only moves the *extraction* part earlier so that the candidate step benefits from it in Sprint 2.

## 8. Measurement and acceptance gates

`eval/candidate_recall.py` (Abhyudit with Heet) runs the generator on `srs_planted.docx` and the labels, and prints:

| Metric | Definition |
|---|---|
| Candidate recall per category | labelled Conflicting / Duplicate / Dependent pairs that became candidates ÷ all such labels |
| Candidate recall, reworded subset | same, for `reworded = true` |
| Recall per signal (ablation) | recall with each signal alone, and with all minus one — shows what each layer contributes |
| Candidate volume | candidates ÷ all pairs (60 requirements = 1,770 pairs), and per requirement |
| LLM calls per 100 requirements | what the run would cost |
| Hard-negative load | how many of the 21 `None` labels became candidates (expected and fine — the LLM must reject them) |

**Gates** (dev split; the held-out split is reported by QA only):

| When | Gate |
|---|---|
| Sprint 2 exit | candidate recall **100 % on the 8 planted conflicts** and ≥ 95 % on all Conflicting + Duplicate + Dependent labels; candidate volume ≤ 10 % of all pairs and ≤ 8 per requirement on average |
| CP1 (S3) | finding recall per category reported with and without context pack and pre-check notes |
| CP2 (S5) | recall split into caught by AI / by rules / missed, including the reworded subset (NFR-37) |

The Sprint 2 report must also give **embedding-only recall** next to hybrid recall, so the gain of this strategy is
visible rather than assumed.

## 9. Risks and how to avoid them

| Risk | Mitigation |
|---|---|
| Lexicon overfits the benchmark (we write phrases for the pairs we already know) | extend `concepts.yaml` only from the **dev** split; report held-out recall separately; add benchmark v2.1 pairs written by someone who has not seen the lexicon |
| Too many candidates → LLM budget | caps in §5; S2 θ tuned to ≤ 3 extra pairs per requirement; rule-signal pairs first when the budget is short |
| Pre-check notes bias the LLM toward "Conflicting" | notes state facts only; with/without ablation at CP1; hard negatives (REQ-004/020 same 5 min, different subject) must stay None |
| Numbers inside IDs, versions, standards ("AES-256", "ISO 27001") read as quantities | strip printed IDs; a stop-list of standard names; require a unit or a bound word |
| Synonyms the lexicon lacks | S1 and S2 still apply; US-56 "raise a concern" records misses; the recall report lists every missed label so the lexicon grows from evidence |
| Different languages or units (min vs minutes, KB vs KiB) | unit table with aliases; English only this semester (scope) |

## 10. Task list for the builders

| Sprint | Owner | Task | Done when |
|---|---|---|---|
| S2 | Keval | `attributes.py` (§4) + `concepts.yaml` + unit/bound tables | unit tests per attribute; the 8 planted conflicts produce the expected attributes |
| S2 | Heet | `candidates.py` `find_candidates` (§5) with S1–S6, ranking, caps; `generate_for_project` persisting `candidate_pairs` | §8 Sprint 2 gate met on the dev split |
| S2 | Parth | migration `0006`: `candidate_pairs.signals jsonb`, `classification_status` incl. `disputed` | up/down in CI |
| S2 | Keval | pre-check notes block (§6) behind a setting so it can be switched off for the ablation | prompt tests: notes escaped, absent when there are no rule signals |
| S2 | Abhyudit | `eval/candidate_recall.py` and the candidate section of `eval/reports/s2.md` | report committed with embedding-only vs hybrid numbers |
| S3 | Heet | incremental mode for US-31 using the same `find_candidates` | single requirement in < 1 s (existing gate) |
| S5 | Keval, Heet | full extractor and `requirement_attributes`; `RuleChecker` findings (`source = rule`) for S3/S6 | test-plan US-58 case passes; CP2 recall by layer |
| S5 | Abhyudit | benchmark v2.1: opposite-modality pairs and reworded pairs written blind to the lexicon | held-out recall reported |
