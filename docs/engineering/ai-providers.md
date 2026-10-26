# AI Providers and Embedding Model

| | |
|---|---|
| **Status** | Decided by the team (24 Oct 2026), recorded as ADR-31. Code still to change — see §6 |
| **Owners** | Keval (LLM client, prompts, budget) · Heet (embedding model, retrieval) · Dhavni didi (secrets in deployment) |
| **Supersedes** | "Anthropic Claude or OpenAI" and "all-MiniLM-L6-v2" in earlier documents, including `docs/planning/v5/` (left unchanged as the approved plan) |

## 1. Decisions

| Concern | Choice |
|---|---|
| **Primary LLM** | **Google Gemini API** |
| **Backup LLM** | **Groq API** — used only when Gemini is unavailable (§3) |
| **Embedding model** | **`BAAI/bge-small-en-v1.5`**, run locally in the worker with Sentence-Transformers (no API call, no cost per embedding) |

Every LLM call still goes through the one `LLMClient` adapter (`app/classification/llm_client.py`, ADR-28 context pack,
NFR-38 budget): classification, clarification questions, suggestions, brief drafting, SRS narrative. Nothing else in the
code may call a provider SDK directly.

## 2. LLM client design

```
Classifier / BriefDrafter / …
        │  complete_json(system, user, Model)   complete_text(system, user)
        ▼
   LLMClient ── budget guard ── validation + one re-ask ──┐
        │                                                 │
        ▼                                                 │
 FallbackTransport( primary = GeminiTransport,            │
                    backup  = GroqTransport )             │
        │ send(system, user) -> text                      │
        ▼                                                 │
  Gemini API  ──(unavailable)──►  Groq API                │
```

* **One transport per provider**, each implementing `send(system, user) -> str` and translating the provider's errors
  into the client's three: `LLMUnavailableError` (retryable: rate limit, 5xx, timeout, network), `LLMRefusedError`
  (safety block), `LLMError` (bad request, configuration).
* **`FallbackTransport`** tries the primary and switches to the backup **only on `LLMUnavailableError`** after the
  primary's own retries. A refusal, a bad request or an invalid reply does **not** fail over — those are not outages,
  and switching would hide a prompt problem.
* **Validation is unchanged:** the reply is parsed into the same Pydantic output models; one re-ask with the validation
  error, on the provider that answered; then `LLMOutputError`. The prompts already embed the JSON Schema, so both
  providers get identical instructions. Each provider's JSON output mode (if used) is an optimisation, not a substitute
  for our validation.
* **Provenance:** every stored AI result records which provider and model produced it (inside
  `findings.original_ai_output`, and on suggestions and SRS sections when those exist), so accuracy can be reported per
  provider and a fallback answer is never mistaken for a primary one.
* **Budget:** `BudgetGuard` counts calls per project regardless of provider (NFR-38). Groq calls during a Gemini outage
  count too.

## 3. Failover rules

| Situation | Behaviour |
|---|---|
| Gemini answers | use it |
| Gemini rate-limited, 5xx, timeout or network error after its retries | send the **same** request to Groq; log a warning with the provider and reason (no prompt text in logs) |
| Gemini refuses (safety block) | return the refusal; no failover |
| Gemini reply fails validation twice | `LLMOutputError`; no failover (it is a prompt or model problem) |
| Both unavailable | `LLMUnavailableError`; Celery retries the task with backoff, then the run waits (US-31 `waiting_budget`/retry behaviour); the document is never marked failed because of the LLM |
| No Gemini key configured, Groq key present | Groq is used as the only provider (development convenience) |
| No key at all | rules-only mode: the brief drafter uses rules, classification is skipped and reported (current behaviour) |

## 4. Embedding model: `BAAI/bge-small-en-v1.5`

| Property | Value | Consequence |
|---|---|---|
| Output size | **384** dimensions | same as all-MiniLM-L6-v2, so `embeddings.vector vector(384)`, `document_sections.embedding` and the HNSW index stay — **no migration** |
| Normalisation | encode with `normalize_embeddings=True` | cosine = dot product; pgvector `<=>` as today |
| Input length | 512 tokens | longer than any single requirement; long document sections are truncated — embed the heading plus the start of the body |
| Query instruction | BGE recommends a retrieval instruction prefix for short *queries* against *passages* | requirement ↔ requirement similarity is symmetric: **no prefix** for embedding requirements or for similar-requirement hints. Use the prefix only if a query-style search box is added later — and then for the query side only |
| `model_version` stored per row | `bge-small-en-v1.5` | `embed_document` already re-embeds rows whose `model_version` differs, so switching models is a one-off re-embedding job, not a schema change |
| Similarity scale | differs from MiniLM | **the default `similarity_threshold` (0.75) was chosen for MiniLM and must be re-tuned** on the benchmark dev split (US-06; ADR-30 candidate gates). Until then rely on top-*k* neighbours, which do not depend on the scale |

Run it on CPU in the worker like the current model; the model is downloaded once per container (cache the Hugging Face
directory in a volume in Compose). Measure similar-hint latency again with `eval/latency/hints_bench.py` after the switch
(target < 500 ms; MiniLM measured 47 ms median, 151 ms p95 on the dev laptop).

## 5. Configuration (proposed names)

| Variable | Example | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | primary; `groq` allowed for development |
| `LLM_FALLBACK_PROVIDER` | `groq` | empty disables failover |
| `GEMINI_API_KEY` | — | secret; server side only (NFR-12) |
| `GEMINI_MODEL` | *to be decided* | see §7 |
| `GROQ_API_KEY` | — | secret |
| `GROQ_MODEL` | *to be decided* | see §7 |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | `60`, `2` | per provider call |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | `model_version` is derived from it |

These replace the single `LLM_API_KEY` / `LLM_MODEL` / `LLM_EFFORT` (the effort setting is specific to the previous
provider). Keys live in `.env` locally and in the hosting provider's secret settings in staging and production; never in
the frontend.

## 6. What has to change in code (for Keval and Heet)

| Area | Change | Owner | Sprint |
|---|---|---|---|
| `llm_client.py` | add `GeminiTransport`, `GroqTransport`, `FallbackTransport`; remove the Anthropic transport; record provider + model in results | Keval | S2, before the first accuracy run |
| `core/config.py`, `.env.example` | variables of §5 | Keval (Parth reviews config) | S2 |
| `requirements.txt` | the official Google Gen AI SDK and the Groq SDK; drop `anthropic` | Keval | S2 |
| tests | `FakeTransport` stays; add tests for the failover rules of §3 (outage → backup; refusal and invalid output → no backup) | Keval | S2 |
| `embeddings/model.py` | `MODEL_NAME = "BAAI/bge-small-en-v1.5"`, `MODEL_VERSION = "bge-small-en-v1.5"`, read from `EMBEDDING_MODEL` | Heet | S2 |
| re-embedding | run the embedding stage over existing documents once (rows with the old `model_version` are re-embedded) | Heet | S2 |
| threshold | re-tune `similarity_threshold` on the dev split; record in `eval/reports/s2.md` | Heet, Abhyudit | S2 |
| benchmark | CP1 accuracy reported **per provider** (Gemini primary run; one Groq run for comparison), with and without the context pack | Abhyudit | S3 |

## 7. Open questions for the team

1. **Which Gemini model** (e.g. a fast/cheap model for classification and a stronger one for SRS narrative, or one model
   for everything)?
2. **Which Groq model** as the backup, and is its accuracy on the benchmark acceptable as a stand-in?
3. **Tiers and quotas:** free or paid tier for each? The free-tier rate limits decide how often failover will trigger
   and whether the per-project budget (default 2,000 calls/month) is realistic.
4. **Data use:** check each provider's terms for whether prompts on the chosen tier may be used to improve their
   models. Requirement text leaves the system only in prompts (system-design §10, NFR-14, NFR-30); a tier that trains
   on prompts may be unacceptable for client documents.
5. **Failover for which calls:** all calls, or classification only (and let suggestions/SRS narrative wait for Gemini)?
6. **Should the backup also be used to break ties** (e.g. a second opinion on low-confidence conflicts)? Not planned;
   it doubles cost.
