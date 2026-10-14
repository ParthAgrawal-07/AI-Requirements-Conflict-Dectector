# LLM Classification Pipeline Design (Sprint 0)

**Role 3: LLM Classification Pipeline**
**Author:** Keval Darji
**Traces to:** US-05, US-07 · FR-11, FR-13, FR-14, FR-15, FR-20 · NFR-07, NFR-15, NFR-17, NFR-21, NFR-22 · DR-07, DR-09 · ADR-02
**Status:** Sprint 0 deliverable (initial prompts + Pydantic output schemas)

---

## 1. What this sprint delivers

| File | What it is |
|---|---|
| `backend/app/classification/schemas.py` | Pydantic models for LLM input and the validated LLM output |
| `backend/app/classification/prompts/*_v1_*.md` | Versioned system + user prompts for the two kinds of LLM call |
| `backend/app/classification/prompting.py` | Loads a prompt version, embeds the output schema, escapes requirement text |
| `backend/tests/classification/` | 34 unit tests for schemas and prompt building (no LLM calls) |

Out of scope until Sprint 2 (T21–T23): calling the LLM, retry/backoff, the Celery task, and
writing `Finding` rows.

## 2. Two kinds of classification call

A `Finding` (`app/models/analysis.py`) is about either a **pair** of requirements or a
**single** requirement. The taxonomy splits the same way, so the classifier makes two kinds
of call:

| Call | Input | Possible output categories |
|---|---|---|
| Pairwise | a candidate pair from the embedding pre-filter (Role 2) | Conflicting, Duplicate, Dependent, None |
| Single | one requirement | Ambiguous, Incomplete, None |

Why split instead of one prompt with all five categories:
- A single requirement can't be "Conflicting" and a pair can't be "Ambiguous". Offering
  impossible answers just gives the model more ways to be wrong.
- Ambiguous/Incomplete checks run once per requirement (N calls), not once per pair.
- Each prompt can be shorter and more focused, which tends to improve accuracy.

`"None"` means "no issue". It is never stored as a `Finding`; `finding_category` returns
Python `None` for it. The string `"None"` matches the benchmark labels
(`sample_docs/planted_conflicts/srs_v1_labels.json`).

## 3. Output schemas

**`PairClassificationOutput`**

| Field | Type | Notes |
|---|---|---|
| `category` | `Conflicting \| Duplicate \| Dependent \| None` | |
| `confidence` | float, 0–1 | FR-13; maps to `findings.confidence` |
| `rationale` | str, 1–1000 chars | FR-14, NFR-15; maps to `findings.rationale` |
| `dependency_direction` | `A_depends_on_B \| B_depends_on_A \| null` | Required **only** for Dependent |
| `evidence` | list[str], max 4 | Verbatim quotes backing the decision (NFR-17) |

**`SingleClassificationOutput`**

| Field | Type | Notes |
|---|---|---|
| `category` | `Ambiguous \| Incomplete \| None` | |
| `confidence`, `rationale` | as above | |
| `vague_terms` | list[str] | Required non-empty for Ambiguous (DR-07: point at the actual word) |
| `missing_information` | list[str] | Required non-empty for Incomplete |

Design decisions:
- **`extra="forbid"`.** If the model invents fields, it isn't following the contract; we'd
  rather reject and retry (Sprint 2) than silently drop data.
- **Cross-field validators.** "Dependent without a direction" or "Ambiguous without naming a
  vague word" are rejected. These are the cases that would otherwise reach the UI as
  unexplainable findings.
- **Whole validated output → `findings.original_ai_output`.** `model_dump(mode="json")` is
  what gets stored, so FR-20 (keep the original AI finding after human correction) has the
  full evidence, not just category + confidence.
- **A test pins the taxonomy.** `test_schema_categories_cover_the_finding_taxonomy_exactly`
  fails if someone adds a `FindingCategory` without updating the schemas, and
  `test_benchmark_labels_fit_the_schemas` fails if the benchmark labels use a category the
  LLM can't output.

## 4. Prompt design

**Category definitions and edge cases come from `sample_docs/planted_conflicts/LABELING_GUIDE.md`.**
The benchmark is labelled with those rules, so the prompts teach the model the same rules.
Key rules carried over:
- Similar wording isn't evidence of an issue (DR-09); includes a dissimilar-sounding conflict example (ADR-01, DR-10).
- Different scope (admin vs. guest) is not a conflict.
- The dependency test: "could one still be satisfied if the other were deleted?" A bare
  cross-reference isn't a dependency.
- Ambiguous vs. Incomplete: "can I point at a specific vague word?" → Ambiguous; otherwise a missing fact → Incomplete.
- Style, formatting, and missing IDs are not issues.

**The JSON Schema is generated from the Pydantic model and embedded in the system prompt**
(`$output_schema`). The prompt and the validator share one source of truth, and a test
checks they match.

**Confidence anchors.** LLM self-reported confidence is poorly calibrated by default, so
the prompt gives concrete bands (0.9+ explicit in text, 0.7–0.89 one assumption, …) and
says "below 0.5 → answer None". This is a starting point only. Real calibration against
the benchmark and user feedback is NFR-22 work (Sprint 4/5).

**Prompt-injection defence (requirement text is data, not instructions).**
1. Requirement text sits inside `<requirement>` tags in the *user* message; rules sit in the
   *system* message.
2. Text and IDs are HTML-escaped, so a requirement containing `</requirement>` can't close
   the tag and smuggle in "instructions". A test plants exactly that attack, and it fails
   if the escaping is removed.
3. The system prompt tells the model explicitly to classify instruction-like text as an
   ordinary requirement.
4. Even if the model is fooled, the output still has to pass schema validation, and every
   finding goes through human review (DR-04).

**Versioning.** Files are named `<kind>_<version>_<system|user>.md`. A new prompt version
is a new file (`pair_v2_system.md`), never an edit to v1, so benchmark results stay
reproducible. `PROMPT_VERSION` in `prompting.py` selects the active one, and Sprint 2
should store it alongside each finding's `original_ai_output`.

## 5. Open questions for the team

1. **Refinement: Dependent or None?** (for Abhyudit) The labelling guide says a near-duplicate
   that "narrows or specializes" another is Dependent (§2, §3), but lists "OAuth2 vs. Google
   OAuth" (a refinement) as None (§7). The v1 prompt resolves this with the dependency test
   (OAuth2 stands on its own → None). Please confirm, or update the guide.
2. **Ambiguous *and* Incomplete at once.** One requirement can have both problems, but a
   `Finding` has one category. v1 picks Ambiguous and mentions the missing fact in the
   rationale. Alternative: allow two findings per requirement.
3. **DR-01 / FR-11 still say 4 categories.** Code follows the adopted 5-category taxonomy
   (ADR-02); the spec text needs the correction already tracked as an open action item.
4. **Evidence quotes come back HTML-escaped** (`&lt;` instead of `<`) because the input was
   escaped. Harmless for display. Sprint 2 can `html.unescape` them before storing.

## 6. Next steps

- **Sprint 1:** run both prompts against `srs_v1.md` by hand / in a notebook, record
  per-category results, iterate to `v2` where the benchmark shows systematic mistakes.
- **Sprint 2 (T21–T23):** provider-agnostic LLM call, validation retry (NFR-07), Celery
  task, persist `Finding` rows with `original_ai_output` + prompt version; precision/recall
  benchmark with Abhyudit (NFR-21).
- **Sprint 4 (US-06, FR-16/17):** make the ambiguity/dependency criteria configurable,
  likely as an extra criteria block injected into the system prompt.
