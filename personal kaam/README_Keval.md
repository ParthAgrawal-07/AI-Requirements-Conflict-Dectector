# Keval — Sprint 0 and Sprint 1

**Merge order:** #5, after Heet (the context pack uses Heet's section search). Merge your own
`feat/keval-sprint0-classification-prompts` **first** — this zip builds on it.

## Status against the plan

| Sprint | Task | Status |
|---|---|---|
| S0 | Prompts with delimited inputs (`prompts/*_v1_*.md`, `prompting.py`, output schemas) | ✅ on your branch (unmerged) |
| S0 | Project-context slot in the prompts | **in this zip** |
| S0 | `LLMClient` adapter: timeout, retries, JSON-schema validation | **in this zip** |
| S0 | Lint (vague-word) catalogue v1 + schema test | **in this zip** |
| S0 | LLM budget design, `BudgetGuard` interface | **in this zip** (design stub, as planned) |
| S1 | US-60 context pack in every prompt, ≤ 1,500 tokens | **in this zip** |
| S1 | Classifier skeleton, output schemas, retries | **in this zip** (schemas from your branch) |
| hand-off | Wire `LLMClient` into Bansil's `get_brief_drafter()` | **in this zip** |

## What this zip contains

| File | |
|---|---|
| `backend/app/classification/llm_client.py` | `LLMClient.complete_json(system, user, Model)` validates into your Pydantic output models, **re-asks once** with the validation error, then raises `LLMOutputError`; `complete_text` for the drafter; budget checked before every call; `AnthropicTransport` (official SDK, model `claude-opus-5-5`, effort from config, SDK retries for 429/5xx, server-side refusal fallback); `FakeTransport` for tests; `get_llm_client()` → `None` without a key |
| `backend/app/classification/budget.py` | `BudgetGuard` protocol + design notes (Redis counter per project and month, `waiting_budget`, 80 % notification); `UnlimitedBudget` until Sprint 3; `CountingBudget` for tests |
| `backend/app/classification/context_pack.py` | `ContextPackBuilder` — summary, actors, glossary terms that occur in the text, up to 3 nearest initial-SRS sections; **only confirmed fields** (`confirmed_values`); HTML-escaped inside `<project_context version="n">`; capped at 1,500 tokens (4 chars/token estimate, conservative) |
| `backend/app/classification/classifier.py` | `Classifier.classify_pair` / `classify_single` (prompt + pack + client) |
| `backend/app/classification/tasks.py` | Celery `classification.classify_pair`: ContextGate first (409 in Setup, no LLM call), stores a `Finding` with `context_version` and the raw output; retries with backoff only when the provider is unavailable |
| `backend/app/classification/prompting.py`, `prompts/*_v1_*.md` | `${context_pack}` slot in both user prompts; a "Project context" section in both system prompts and `<project_context>` declared as data in "Untrusted input" |
| `backend/app/lint/catalogue.json` | 11 rules `{id, category, pattern, message, hint, severity}`: vague (speed, usability, quality, quantity, hedges), unbounded (etc., absolutes), TBD, passive, missing actor, weak modal — regexes valid in both Python and JS so the composer runs them with no AI |
| `backend/app/context/drafter.py` | `get_brief_drafter()` uses the LLM when `LLM_API_KEY` is set, else Bansil's rules drafter |
| `backend/app/core/config.py`, `.env.example` | `LLM_MODEL`, `LLM_EFFORT` (default `low`), `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`; `LLM_API_KEY` empty by default (was a fake placeholder value) |
| `backend/requirements.txt` | **adds `anthropic>=0.70`** (the official SDK) |
| tests | `tests/classification/test_llm_client.py`, `test_context_pack.py`, `test_classifier_tasks.py`, `test_lint_catalogue.py` |

## Done-when (guide)

* S0: "Adapter unit tests with a fake model; catalogue JSON validated by a schema test" ✅
* S1: "Fake-model tests pass" ✅ — and the context pack: AI-drafted fields never reach the prompt, ≤ 1,500 tokens even
  with huge sections, an injected `</project_context>` cannot close the block.

## Decisions to review

* **Model and effort**: defaults `claude-opus-5-5` at effort `low` (classification is short and frequent). Tune effort
  with the CP1 benchmark run, not by guessing; both are environment variables.
* **No structured-output mode**: replies are validated on our side against your schemas (the prompts already embed the
  JSON Schema), so the same code works whatever the schema contains.
* **Provider**: only `anthropic` is implemented; `LLM_PROVIDER=openai` raises a clear error.
* No real API call was made while building this — everything was tested with `FakeTransport`. Run one manual call with
  a real key before Sprint 2.
