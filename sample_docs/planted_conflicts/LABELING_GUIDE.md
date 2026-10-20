# Labeling Guide — Planted Issues in SRS v1

## Purpose

This guide defines how to label planted issues in `srs_v1.md` for the
labeled benchmark set required by `docs/engineering/test-plan.md` §3
(precision/recall/F1 per category, NFR-21, NFR-22).

Two people label the SRS independently. This guide is the shared contract;
if labelers disagree, the guide is presumed unclear and gets updated, not
the labels.

> **On examples:** IDs shown in this guide (`REQ-###`) are illustrative
> only. The actual SRS and its labels live in `srs_v1.md` and
> `srs_v1_labels.json`. Where example IDs overlap with each other across
> sections, treat them as independent illustrations of the rule, not as
> references to a single underlying requirement.

## Scope

- **Input:** `srs_v1.md` — a mock SRS consisting of `REQ-###` requirement
  lines, one per line. No headings, no prose, no numbering besides the IDs.
- **Output:** `srs_v1_labels.json` — ground-truth labels for a subset of
  requirement pairs and single requirements in `srs_v1.md`.
- **Consumers:** the classifier (Role 3) and its evaluation harness.

## Categories

The five categories are authoritative per **ADR-02** and are enumerated in
`backend/app/models/enums.py::FindingCategory`. Plus `None` for hard
negatives (see test-plan §3).

- Conflicting
- Duplicate
- Ambiguous
- Incomplete
- Dependent
- None (explicit "not an issue")

Labels in `srs_v1_labels.json` use these exact capitalized strings, matching
the `findings.category` check constraint in the initial migration.

## Pairwise vs. single-requirement

Per `backend/app/models/analysis.py`, a finding is either:

- **Pairwise** — involves two requirements (`r1`, `r2`). Categories:
  Conflicting, Duplicate, Dependent, and also None.
- **Single-requirement** — a property of one requirement (`r1` only).
  Categories: Ambiguous, Incomplete.

The labels JSON reflects this:

```json
{"r1": "REQ-003", "r2": "REQ-014", "category": "Conflicting", "note": "..."}
{"r1": "REQ-008", "category": "Ambiguous", "note": "..."}
{"r1": "REQ-005", "r2": "REQ-009", "category": "None", "note": "..."}
```

## 1. Conflicting (pairwise)

**Definition:** Two requirements state incompatible behavior for the same
subject under the same conditions. Both cannot be satisfied simultaneously.

**Examples:**
- `REQ-001: The system shall store all user data encrypted at rest.` vs.
  `REQ-101: User preference records shall be stored in a plaintext database.`
- `REQ-102: API requests shall time out after 2 seconds.` vs.
  `REQ-103: API requests shall be permitted up to 10 seconds before timeout.`

**Edge cases:**
- Different *scope* is not a conflict. "Admin sessions expire after 5 min"
  and "user sessions expire after 30 min" — different subjects, not a conflict.
- A refinement (one requirement is a subset of another) is **Dependent** or
  **Duplicate**, not Conflicting.
- **Include dissimilar-sounding pairs** — a true conflict can exist between
  requirements with low embedding similarity (ADR-01, DR-10). Example:
  `REQ-001` (encrypt at rest) vs. `REQ-104` (recoverable plaintext by admins).
  These are the highest-value labels in the benchmark: they test whether
  the classifier does more than similarity matching.

## 2. Duplicate (pairwise)

**Definition:** Two requirements express the same behavior in different
words. Both are semantically equivalent; either could be removed without
losing information.

**Examples:**
- `REQ-201: The system shall support multi-factor authentication.` vs.
  `REQ-202: MFA shall be available to all users.`
- `REQ-203: The system shall record all failed login attempts.` vs.
  `REQ-204: Failed authentication events must be logged by the system.`

**Edge cases:**
- Partial overlap is not Duplicate — it is **Dependent**.
- Same wording in different scope (admin vs. user) is not Duplicate.
- Near-duplicate with a meaningful difference ("shall log failed logins" vs.
  "shall log failed logins with source IP") is **Dependent**, not Duplicate.

## 3. Dependent (pairwise)

**Definition:** One requirement relies on another to be satisfiable, without
restating it. Removing or violating the depended-upon requirement makes the
dependent one impossible to satisfy.

**Examples:**
- `REQ-301: The system shall email a confirmation to the user.` depends on
  `REQ-302: The system shall store a verified email address for every user.`
- `REQ-303: Retention periods shall be configurable per data category.` is
  depended on by `REQ-304: User data shall be retained for 7 years.`

**Edge cases:**
- A cross-reference like "as specified in REQ-###" is not Dependent by
  itself; there must be a functional dependency, not just a citation.
- Refinement vs. Duplicate: if R_A is fully contained in R_B (same
  behavior, same subject, one is just wordier), label Duplicate. If R_A
  narrows or specializes R_B in a way that adds new constraints, label
  Dependent.

## 4. Ambiguous (single)

**Definition:** A requirement's *language* allows more than one reasonable
interpretation of what must be built or verified. The problem is with the
words, not with missing information.

**Examples:**
- `REQ-401: The system shall respond promptly to user input.`
  ("promptly" has no numeric bound — one reader may assume 100 ms, another 5 s.)
- `REQ-402: The user interface shall be user-friendly.`
  ("user-friendly" has no measurable criterion.)

**Edge cases:**
- "Shall" vs. "should" alone is style, not ambiguity.
- Ambiguous applies to a *single requirement in isolation* — if two
  requirements are involved, use one of the pairwise categories.
- **Vague-word vs. missing-fact rule (see §6).** A vague term like "fast"
  or "promptly" is Ambiguous. A requirement that is clear about what it
  wants but omits a necessary quantity is Incomplete.

## 5. Incomplete (single)

**Definition:** A requirement cannot be implemented or verified because it
omits information the reader would need. The wording may be clear; the
problem is a missing fact.

**Examples:**
- `REQ-501: The system shall support multiple document formats.`
  (which formats? PDF, DOCX, TXT — the reader cannot implement.)
- `REQ-502: The system shall maintain 99.9% uptime.`
  (over what measurement window? per month, per quarter?)

**Edge cases:**
- A vague word is Ambiguous, not Incomplete (see the rule in §6).
- A requirement without an ID is a formatting bug, not an issue.
- A requirement missing a *rationale* is not Incomplete — rationale is
  optional in an SRS. Only implementation/verification-blocking gaps count.

## 6. The Ambiguous vs. Incomplete boundary

This is the single most likely source of label disagreement, so it gets
an explicit rule. `docs/engineering/test-plan.md` §2 lists
*"a requirement missing acceptance criteria for a vague term ('fast')"*
as expecting either category — this guide picks one and sticks to it:

**Rule:** Label **Ambiguous** when the problem is a vague word the
requirement uses. Label **Incomplete** when the requirement uses clear
words but omits a necessary fact (quantity, format, window, target).

Quick test: *Can I identify a specific word in the requirement that
creates the problem?*

- **Yes** → the word is vague → **Ambiguous**.
- **No, the words are fine but something is missing** → **Incomplete**.

Worked example: `REQ-401: The system shall respond promptly to user input.`
The problem is the word "promptly" (what is prompt?). → **Ambiguous**.

Worked example: `REQ-502: The system shall maintain 99.9% uptime.`
No vague word — "uptime," "99.9%," and "maintain" are all clear. What is
missing is the measurement window. → **Incomplete**.

## 7. None (pairwise)

**Definition:** A pair that superficially resembles an issue but is not one.
Used to give the classifier hard negatives and to make precision measurable.

**Examples (from test-plan §2 and typical SRS traps):**
- **Different scope, same rule.** `REQ-701: Admin sessions shall expire
  after 5 minutes.` vs. `REQ-702: Guest sessions shall expire after 5
  minutes.` Same policy, different subjects → `None`.
- **Refinement.** `REQ-703: The system shall support OAuth2.` vs.
  `REQ-704: The system shall support Google OAuth.` One is a subset of
  the other — but here it is not a dependency because OAuth2 stands on its
  own; the second simply narrows a supported provider → `None`.
- **Complementary.** `REQ-705: The system shall log failed logins.` vs.
  `REQ-706: The system shall alert after five consecutive failed logins.`
  One triggers the other; neither contradicts, duplicates, nor depends on
  the other for satisfiability → `None`.

**Edge cases:**
- `None` is *not* a catch-all. Only label pairs as `None` when they belong
  to the benchmark as hard negatives. A random unlabeled pair is not
  the same as a labeled `None` pair.
- `None` applies only to pairwise candidates; it is never used for a single
  requirement.

## 8. Categories explicitly NOT used

Per ADR-02, some adjacent concepts are out of scope for this benchmark:

- **Security / compliance** concerns — those are policy findings, not
  requirements-engineering findings.
- **Style violations** — "shall" vs. "must" is not an issue category.
- **Naming/formatting** — the taxonomy is about requirement semantics.
- **Cross-document** issues — the benchmark is single-document.

## 9. File formats

### `srs_v1.md`

One `REQ-###` per line. No headings, no prose, no numbering besides the IDs.
This is what the Sprint 0 segmenter (`backend/app/ingestion/segmentation/`)
expects: line-by-line regex matching against `REQUIREMENT_ID_PATTERN`.

Example:

```
REQ-001: The system shall authenticate users with a username and password.
REQ-002: The system shall store all user data encrypted at rest using AES-256.
REQ-003: The system shall log every successful login attempt.
```

Rationale for flat format: the Sprint 0 segmenter treats *every* non-empty
line without a matching ID as a requirement (fallback `UNKNOWN-…`). Headings
and prose would create spurious `UNKNOWN-*` requirements and pollute the
benchmark. Section context (if any) lives in this guide, not in the SRS.

### `srs_v1_labels.json`

One JSON object. Uses the five capitalized category strings plus `"None"`.
Pairwise entries have `r1` and `r2`. Single entries have `r1` only. Every
entry has a `note` explaining the rationale in one sentence.

```json
{
  "categories": ["Conflicting", "Duplicate", "Ambiguous", "Incomplete", "Dependent", "None"],
  "labels": [
    {"r1": "REQ-002", "r2": "REQ-014", "category": "Conflicting", "note": "Encryption at rest contradicts plaintext preference storage."},
    {"r1": "REQ-008", "category": "Ambiguous", "note": "'Promptly' has no numeric bound."}
  ]
}
```

## 10. Process

1. Author writes `srs_v1.md` and a first pass of `srs_v1_labels.json`.
2. Second labeler labels independently — before seeing the author's labels.
3. Reconcile: any disagreement is discussed against this guide.
4. Any disagreement that this guide cannot resolve is a **guide bug** —
   update the guide, then re-label the affected entries.

**Coverage target:** the labels JSON should contain at least 3 entries
per category, plus at least 4 `None` hard negatives. Per-category
precision/recall is only meaningful at that scale (test-plan §3).

## 11. Versioning

- `srs_v1.md` — the SRS text.
- `srs_v1_labels.json` — the labels for that SRS.
- Subsequent SRS revisions get new suffixes (`srs_v2.md`, `srs_v2_labels.json`).
  Do not edit `v1` after it has been used for a benchmark run.
