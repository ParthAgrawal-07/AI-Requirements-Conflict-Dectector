# Database Documentation

**ER Diagram, Table Definitions, and Data Dictionary**

| | |
|---|---|
| **Engine** | PostgreSQL + pgvector extension |
| **Status** | Implemented through migration `0004` (Sprint 0, rev. 5 plan). Later migrations add the rest — see the design update §4.3 |

---

## 1. ER Diagram

```mermaid
erDiagram
  WORKSPACE ||--o{ PROJECT : contains
  WORKSPACE ||--o{ MEMBERSHIP : has
  USER ||--o{ MEMBERSHIP : "belongs through"
  ROLE ||--o{ MEMBERSHIP : "assigned in"
  ROLE ||--o{ ROLE_PERMISSION : grants
  PROJECT ||--o{ PROJECT_MEMBER : team
  PROJECT ||--o{ DOCUMENT : holds
  DOCUMENT ||--o{ REQUIREMENT : contains
  REQUIREMENT ||--|| EMBEDDING : has
  REQUIREMENT ||--o{ CANDIDATE_PAIR : "appears in (as A or B)"
  CANDIDATE_PAIR ||--o{ FINDING : classified_into
  FINDING ||--o| CLARIFICATION : generates
  FINDING ||--o{ AUDIT_LOG : records
  REQUIREMENT ||--o{ REQUIREMENT_VERSION : tracks
```

## 2. Tenancy tables (Sprint 0 — migration 0004)

People belong to workspaces through **memberships**; the old single `users.role` / `users.workspace_id`
columns are gone. See `roles-and-access.md` for how they are used.

### 2.0a projects

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| workspace_id | UUID (FK) | RESTRICT; `(workspace_id, name)` unique |
| name / description | varchar(120) / text | |
| status | `setup` / `active` / `archived` | New projects start in `setup` (FR-103); no analysis until `active` |
| context_version | int, default 0 | Current confirmed context version (written by the context service, US-60). *Created here rather than in 0011 — see the migration docstring* |
| similarity_threshold, confidence_threshold | float 0–1 | Defaults 0.75 / 0.5 (team-tunable, US-06) |
| llm_budget_monthly_calls | int ≥ 0 | Default 2000 |
| chat_detection_enabled | bool, default false | Chat text reaches the LLM only if a manager enables it (SX-04) |
| required_approvals | int 1–3 | Default 1 |
| created_by | UUID (FK -> users, nullable) | |

### 2.0b roles and role_permissions

`roles`: `id`, `workspace_id` (NULL for the nine platform defaults), `name`, `description`, `is_default`.
A CHECK keeps defaults global and custom roles per workspace; partial unique indexes keep names unique
(among defaults, and within a workspace). `role_permissions`: PK `(role_id, permission)`, `permission` is a name
from `app.core.permissions.PERMISSIONS`, `protected_only` marks "held for protected requirements only".
The nine default roles and their grants are seeded by migration 0004; `tests/db/test_default_roles.py` checks
the rows against `app/core/permissions.py`.

### 2.0c memberships and project_members

`memberships`: `user_id`, `workspace_id`, `role_id` (RESTRICT — a role in use cannot be deleted),
`stakeholder_group`, `joined_at`, `ended_at`. **At most one active membership per (user, workspace)** — a
partial unique index `WHERE ended_at IS NULL`; ended rows are history, so rejoining never edits old rows.
`project_members`: PK `(project_id, user_id)`, optional `role_override_id` (project-level role, FR-79).

### 2.0d Columns added to existing tables

| Table | Column | Notes |
|---|---|---|
| users | `platform_role` | NULL, `platform_admin` or `service`. Replaces `role` and `workspace_id` |
| documents | `project_id` | NOT NULL FK; `workspace_id` stays and equals the project's |
| documents | `import_mode` | `baseline` (requirements Approved) or `proposals` (Proposed, default) — FR-01 |
| documents | `stakeholder_group` | optional, copied onto the document's requirements (FR-05) |
| requirements | `project_id` | NOT NULL FK, denormalised from the document |
| requirements | `state` | Proposed / Under_Review / Approved / Rejected / Implemented / Deprecated (default Proposed) |
| requirements | `origin` | document / post / change_request (default document) |
| requirements | `owner_id` | nullable FK -> users |
| findings | `severity` | now `low` / `medium` / `high` only (migration 0003; `critical` became `high`) |

`workspaces.name` is **not unique** (migration `0004a`): a platform-wide unique name would let one tenant learn that
another tenant's workspace exists. Workspaces are identified by id.

Existing data is backfilled by 0004: one `active` project per workspace, one membership per user (the first
admin — else the earliest user — becomes Owner), existing documents count as baseline imports and their
requirements as `Approved`.

## 2.1 Original tables (7)

### documents

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Primary key |
| filename | varchar | Original uploaded filename |
| format | varchar | pdf / docx / txt / reqif — FR-01 |
| status | varchar | queued / processing / done / failed — FR-02, US-03 |
| workspace_id | UUID (FK) | Access scoping — FR-38 |
| uploaded_by | UUID (FK -> users) | Provenance — FR-05 |
| uploaded_at | timestamp | |

### requirements

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | |
| source_req_id | varchar, nullable | Preserves original REQ-ID if present — FR-04, DR-03 |
| body | text | Extracted requirement statement |
| stakeholder_group | varchar, nullable | Provenance — FR-05, DR-11 |
| is_protected | boolean, default false | Compliance-critical flag — FR-21, DR-05 |
| current_version | int | FK target into requirement_versions |

### requirement_versions

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| requirement_id | UUID (FK) | |
| version_no | int | |
| body_snapshot | text | Prior text at this version — FR-26, DR-08 |
| changed_by | UUID (FK -> users) | |
| changed_at | timestamp | |

### embeddings

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| requirement_id | UUID (FK, unique) | |
| vector | vector(384) | all-MiniLM-L6-v2 output — FR-07, FR-08 |
| model_version | varchar | For re-embedding on model upgrade |

### candidate_pairs

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| requirement_a_id | UUID (FK) | |
| requirement_b_id | UUID (FK) | |
| similarity_score | float | Above configurable threshold — FR-09, FR-10 |
| generated_at | timestamp | |

### findings

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| candidate_pair_id | UUID (FK, nullable) | Null for single-requirement findings (e.g., Incomplete) |
| category | enum | Conflicting / Duplicate / Ambiguous / Incomplete / Dependent |
| confidence | float (0-1) | FR-13 |
| rationale | text | Natural-language explanation — FR-14 |
| status | varchar | flagged / confirmed / dismissed / merged / reclassified — FR-18 |
| original_ai_output | jsonb | Preserved even after human correction — FR-20 |
| severity | `low` / `medium` / `high`, nullable | US-08 (FR-42) — `critical` retired in migration 0003 |

### audit_log

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| finding_id | UUID (FK, nullable) | |
| actor_id | UUID (FK -> users) | |
| action | varchar | e.g. viewed_protected, dismissed, merged — FR-19, FR-36, NFR-13 |
| at | timestamp | |

*An 8th planned table, `clarifications` (finding_id, question, resolution — FR-22/FR-23), is intentionally kept 1:1 with findings and is described inline in the class diagram in `diagrams.md` rather than repeated here.*

## 3. Indexing Notes

- `embeddings.vector` needs an IVFFlat or HNSW pgvector index for similarity search to stay within the NFR-01/NFR-02 performance targets at scale.
- `candidate_pairs` should be indexed on `(requirement_a_id, requirement_b_id)` to support fast lookups from the graph view (FR-29).
- `audit_log` should be append-only with no update/delete permission at the application layer, consistent with FR-36 (exportable, complete audit trail).
