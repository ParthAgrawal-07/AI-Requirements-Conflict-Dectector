# Contract — composer fields, drafts, EARS templates and the project brief (Bansil)

| | |
|---|---|
| **Producer** | Bansil (ingestion and authoring) |
| **Consumers** | Pranshu (composer UI) · Keval (EARS wording, lint, context pack, brief prompt) · Abhijeet (setup wizard, Setup banner) · Heet (section embeddings) · Abhyudit / Affan (tests) |
| **Status** | Sprint 0 contracts agreed; the brief, context service and API are implemented in Sprint 1 (US-60). Composer posting and drafts persistence come with US-30 (Sprint 3) |
| **Code** | `backend/app/intake/` (EARS, composer and draft schemas) · `backend/app/context/` (brief schema, drafter, service) · `backend/app/api/context.py` · migration `0011_project_context` |

## 1. EARS templates (with Keval — FR-81, DR-18)

Five patterns plus free text. The UI fetches them from `GET /composer/templates` and builds its chips, labelled slots
and live preview from the response; the backend renders the stored sentence with the same definition
(`app.intake.ears.render_statement`), so preview and stored text cannot drift.

| `template` | Chip | Sentence | Slots |
|---|---|---|---|
| `ubiquitous` | Always | The {system} shall {response}. | system, response |
| `event_driven` | When… | When {trigger}, the {system} shall {response}. | trigger, system, response |
| `state_driven` | While… | While {state}, the {system} shall {response}. | state, system, response |
| `unwanted_behaviour` | If…then | If {condition}, then the {system} shall {response}. | condition, system, response |
| `optional_feature` | Where… | Where {feature}, the {system} shall {response}. | feature, system, response |
| `free_text` | Free text | {statement} | statement |

Rendering: whitespace is collapsed; a leading "the" in *system* and "shall" in *response* are dropped (the pattern has
them); trailing `.,;` in a slot is dropped (the pattern adds the full stop). Free text is kept as typed (trimmed). Free
text is allowed but the lint flags it (DR-18, Keval). Slot limits: 500 characters, statement 4,000.

## 2. Composer field schema (with Pranshu — FR-55, FR-81)

`ComposerFields` — the body of *Propose requirement* (route arrives with US-30):

| Field | Type | Required | Notes |
|---|---|---|---|
| `template` | one of §1 | yes | |
| `slots` | `{slot: text}` | yes | every slot of the template must be filled |
| `type` | `functional` · `non_functional` · `constraint` | yes | |
| `priority` | `must` · `should` · `could` · `wont` | yes | MoSCoW |
| `stakeholder_group` | text ≤ 120 | no | default: the poster's group |
| `owner_id` | user id | no | default: the poster (US-36) |
| `tags` | ≤ 10 × text ≤ 40 | no | trimmed, de-duplicated |
| `rationale` | text ≤ 2,000 | no | |
| `acceptance_criteria` | ≤ 10 × `{given, when, then}` | no | each part 1–500 characters |
| `channel_id` | channel id | no | where the requirement card is posted; null = the group's channel |

Unknown fields are rejected (`422`). The requirement `body` is the rendered sentence and is never rewritten later
(FR-04).

## 3. Drafts model (with Pranshu)

Drafts autosave every 5 s and are private to their author (FR-81).

* **Table** `requirement_drafts` (migration `0006`, Sprint 2–3): `id`, `author_id`, `project_id`, `fields` (jsonb,
  `DraftFields`), `created_at`, `updated_at`. One author sees only their own drafts; a draft is deleted when it is
  proposed.
* **`DraftFields`**: the same fields as `ComposerFields`, all optional, so half-written work saves.
* **API** (design update §9): `GET /me/drafts?project=` · `POST /me/drafts` · `PATCH /me/drafts/{id}` (replace
  `fields`) · `DELETE /me/drafts/{id}`. Each item (`RequirementDraftRead`) is `{id, project_id, fields, preview,
  updated_at}`; `preview` is the rendered sentence, or null while slots are empty.

## 4. Project brief schema (with Keval — FR-103, US-60)

| Field | Label in the wizard | Required | Stored as |
|---|---|---|---|
| `purpose` | Purpose and problem | yes | `purpose` text |
| `scope` | Scope (in and out) | yes | `scope_in`, `scope_out` text — **both** needed |
| `actors` | User classes and actors | yes | `actors` list of names (≤ 30, ≤ 120 chars, de-duplicated) |
| `environment` | Operating environment and domain | yes | `environment` text |
| `glossary` | Glossary | no | `glossary` list of `{term ≤ 80, meaning ≤ 500}` (≤ 200) |
| `constraints` | Constraints and assumptions | no | text |
| `quality_goals` | Quality goals | no | text |
| `regulations` | Applicable regulations | no | text |
| `references` | Reference links | no | list of `{title, url (http/https) or null}` (≤ 50) |

Text fields are ≤ 4,000 characters; blank text counts as empty.

**Field status.** Each filled field has `ai_drafted` (from the initial SRS) or `confirmed`. Editing a field confirms
it; naming it in `confirm` accepts the AI draft as it is. The project is **Active** once all four required fields are
filled and confirmed.

**Versions.** Every save is a new `project_contexts` row (`version` 1, 2, …) with `created_by` and `reason`.
`projects.context_version` points at the newest version whose required fields are all confirmed (0 in Setup). After
activation an edit needs a `reason`, cannot empty a required field, and the response says how many open findings a
re-run would cover.

**Summary.** On confirmation the service stores `summary` (≤ 300 words) built from the *confirmed* fields only.
Keval's `ContextPackBuilder` reads `summary`, `actors`, `glossary` and the confirmed version number from
`confirmed_context(db, project)`.

## 5. Brief drafting from the initial SRS (FR-104)

* Extraction now returns **sections** (heading + verbatim body); the worker stores them in `document_sections`
  (`embedding` stays NULL for Heet's stage).
* While the project is in Setup, the worker drafts the brief from the descriptive sections (chapters 1–2 of an
  IEEE 830 / ISO 29148 outline, or headings such as Purpose, Scope, User Classes, Operating Environment,
  Definitions, References). Confirmed fields are never overwritten; drafting never activates the project; a drafting
  failure never fails the document.
* **LLM path:** `BriefDrafter(llm=...)` takes a `(system, user) -> text` callable. The prompt
  (`app/context/prompts/brief_v1_system.md`) marks the `<document>` block as data; the reply must be the brief JSON;
  one retry with the validation error, then fall back. **Hand-off to Keval:** wire `LLMClient` into
  `get_brief_drafter()` (budget guard included) and own the prompt wording from here.
* **Rules path:** used until the LLM is wired, and as the fallback. Fills fields from matching headings.

## 6. The ContextGate message (with Parth)

`app.context.service.ensure_analysis_allowed(db, project)` wraps Parth's `ensure_project_active` and passes the labels
of the missing fields, so the `409 project_in_setup` message reads e.g. *"… Missing: Scope (in and out), User classes
and actors."* Call it wherever analysis, the composer or a change request would start.
