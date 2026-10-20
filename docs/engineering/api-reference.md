# API Documentation

**Planned FastAPI Endpoints**

| | |
|---|---|
| **Base path** | `/api/v1` |
| **Auth** | Bearer JWT (FR-37) on every endpoint except `/auth/login` and `/auth/signup`. Every route also declares the **permission** it needs (`roles-and-access.md`) |
| **Status** | Implemented (Sprint 0–1, rev. 5 plan): section 0 below. Everything else is planned. |

---

## 0. Implemented endpoints (Sprint 0–1)

`{w}` = workspace id, `{p}` = project id. "Needs" is the permission from the catalogue; a caller who is
**not a member** of the workspace always gets **404** (never 403), and an unknown id is 404 too.

| Method & Path | Needs | Purpose | Story |
|---|---|---|---|
| `POST /auth/login` | public | Authenticate, issue JWT | US-19 |
| `POST /auth/signup` | public (+ a join code) | Create an account **with a join code**; rate-limited | US-19 |
| `GET /auth/me` | signed in | The user and every workspace they belong to, with their role in each | US-19, US-24 |
| `GET /me/permissions?project={p}` or `?workspace={w}` | signed in | The caller's effective permissions there (drives the UI; never the gate) | US-27 |
| `POST /workspaces` | platform admin (or any user if `ALLOW_USER_WORKSPACE_CREATION`) | Create a workspace; you become its Owner | US-24 |
| `GET /workspaces` | signed in | The caller's workspaces with their role | US-24 |
| `GET /workspaces/{w}` | `view` | One workspace | US-24 |
| `PATCH /workspaces/{w}` | `workspace.manage` | Rename (names are not unique) | US-24 |
| `POST /workspaces/{w}/projects` | `project.manage` | Create a project (starts in `setup`) | US-24 |
| `GET /workspaces/{w}/projects` | `view` | List projects (`include_archived`, `limit`, `offset`) | US-24 |
| `GET /projects/{p}` | `view` | One project, incl. `status` and `analysis_enabled` | US-24 |
| `PATCH /projects/{p}` | `project.manage` | Edit name, description, thresholds, budget, approvals, chat detection. **Not** the status | US-24 |
| `POST /projects/{p}/documents` | `doc.upload` (proposals) / `baseline.manage` (baseline) | Upload an SRS, queue extraction | US-01 |
| `GET /projects/{p}/documents` | `view` | List the project's documents | US-03 |
| `GET /documents/{id}` | `view` | Document status and progress | US-03 |
| `GET /projects/{p}/requirements` | `view` | Paginated, searchable, filterable requirement list | US-04 |

**Changed from Sprint 1 (old plan):** `POST /documents`, `GET /documents` and `GET /documents/{id}/requirements`
no longer exist; documents belong to a project, and requirements are listed per project
(`GET /projects/{p}/requirements?document_id=`). `GET /documents/{id}` is unchanged apart from new fields.

### `POST /auth/signup`  *(US-19)*

```
Request:  { "email", "password" /* ≥ 12 chars */, "full_name", "code" /* join code or invite token */ }
Response 201:
{ "access_token", "token_type": "bearer", "expires_in",
  "user": { "id", "email", "full_name", "platform_role": null, "is_active", "created_at" },
  "join_status": "joined" | "pending_approval",   // pending: a manager must approve the join request
  "workspace_id": "uuid" | null }
```

The account and its membership are created in **one transaction**: an invalid, expired, used-up or revoked code
creates nothing. Errors: `400 weak_password`; **`400 signup_refused`** — returned both for an unusable code (invalid, expired,
used-up, revoked) and for an e-mail that already has an account, with the *same* status, code and message, so the
endpoint cannot be used to find out which e-mails are registered (existing users sign in and enter the code
instead); `429 too_many_requests` with `Retry-After` (5 attempts per minute per client address and per e-mail —
`SIGNUP_ATTEMPTS_PER_MINUTE`; behind a reverse proxy set `TRUSTED_PROXY_HOPS`). If Redis is unreachable the limit
falls back to a per-process counter instead of failing sign-up.

### `GET /me/permissions`  *(US-27)*

```
GET /me/permissions?project=<uuid>          (or ?workspace=<uuid>)
Response 200: { "workspace_id", "project_id" | null,
                "role": { "id", "name", "is_default" },       // effective role: the project override if any
                "permissions": ["view", "doc.upload", ...],   // sorted catalogue names
                "protected_only": ["finding.review"] }        // held for protected requirements only
```

`400 scope_required` if neither parameter is given; `404` if the caller is not a member.

### Projects  *(US-24)*

`POST /workspaces/{w}/projects` body: `name` (required, ≤ 120), optional `description`, `similarity_threshold`
(0–1, default 0.75), `confidence_threshold` (0–1, default 0.5), `llm_budget_monthly_calls` (default 2000),
`required_approvals` (1–3, default 1), `chat_detection_enabled` (default false). Response `201` + `Location`.
Unknown fields — notably `status` — are rejected with `422`: a project becomes `active` by confirming its
context (US-60), never by sending a flag. `409` if the workspace already has a project with that name.

While a project is in `setup`, `analysis_enabled` is `false`: analysis, the composer and change requests are
refused with **`409 project_in_setup`** (the message names the missing context fields). Uploading the initial
SRS and extracting its requirements is allowed in setup.

## 1. Endpoint Summary (10 planned)

| # | Method & Path | Purpose | FR trace |
|---|---|---|---|
| 1 | `POST /auth/login` | Authenticate, issue JWT | FR-37 |
| 2 | `POST /projects/{p}/documents` | Upload an SRS document (implemented — see section 0) | FR-01, FR-02 |
| 3 | `GET /documents/{id}` | Get document status/progress | US-03 |
| 4 | `GET /projects/{p}/requirements` | List requirements (implemented — see section 0) | FR-04, US-04 |
| 5 | `PATCH /requirements/{id}` | Correct extraction/segmentation, or edit text (triggers impact analysis) | FR-06, FR-24 |
| 6 | `GET /documents/{id}/findings` | List classified findings for a document | FR-27, FR-28 |
| 7 | `PATCH /findings/{id}` | Confirm / dismiss / merge / reclassify a finding | FR-18, FR-20 |
| 8 | `GET /findings/{id}/clarification` | Get or generate the clarification question | FR-22, FR-23 |
| 9 | `GET /requirements/{id}/impact` | Get change-impact analysis for a requirement | FR-24, FR-25 |
| 10 | `GET /workspaces/{id}/dashboard` | Aggregated counts + graph data | FR-27, FR-29 |

## 2. Selected Endpoint Detail

### `POST /projects/{p}/documents`  *(implemented — US-01)*

Uploads an SRS document into a project and enqueues extraction (FR-01, FR-02). Allowed while the project is in
`setup` (the initial SRS is uploaded then).

```
Request:  multipart/form-data
            file               PDF (.pdf) or Word (.docx); max MAX_UPLOAD_SIZE_MB, default 25
            import_mode        "proposals" (default) | "baseline"
            stakeholder_group  optional, ≤ 120 chars; copied onto the document's requirements
Response 202  + Location: /api/v1/documents/{document_id}
{
  "document_id": "uuid",
  "project_id": "uuid",
  "status": "queued",                        // queued | processing | done | failed
  "filename": "srs_v3.docx",
  "format": "docx",
  "size_bytes": 36686,
  "progress_percent": 0,
  "error_message": null,
  "requirement_count": 0,
  "import_mode": "proposals",
  "stakeholder_group": null,
  "uploaded_by": "uuid",
  "uploaded_at": "2026-10-01T04:40:38Z",
  "duplicate_of": null                       // id of an earlier identical upload in this project, else null
}
```

**Import mode** decides the requirements' state: `baseline` → **Approved** (needs `baseline.manage`: Owner, Admin,
Project Manager, Business Analyst); `proposals` → **Proposed** (needs `doc.upload`, which also covers Developer,
QA Engineer and Stakeholder). `duplicate_of` is informational: a re-upload is still accepted and processed.

**Errors** (body `{"error": {"code", "message", "request_id"}}` — `message` is written to be shown to the user):

| Status | `code` | When |
|---|---|---|
| 400 | `unsupported_file_type` | extension is not `.pdf` / `.docx` (legacy `.doc`, `.txt`, ReqIF get a specific hint) |
| 400 | `empty_file` | zero bytes |
| 400 | `corrupted_file` | content is not the claimed format, or a PDF/DOCX is truncated/unreadable |
| 400 | `file_content_mismatch` | e.g. a Word file renamed `.pdf`, or a password-protected Office file |
| 400 | `unsafe_file` | a `.docx` that expands to an unreasonable size (zip bomb) |
| 403 | `forbidden` | the role lacks `doc.upload` (Viewer, Compliance Reviewer), or lacks `baseline.manage` for a baseline import |
| 404 | `not_found` | the project does not exist or the caller is not a member of its workspace |
| 413 | `payload_too_large` | larger than the limit — refused **before** the body is read when the client declares its size, and cut off mid-stream when it doesn't |
| 422 | `validation_error` | no `file` part, or an unknown `import_mode` |
| 503 | `queue_unavailable` | the job queue is down; nothing was stored — retry |

Validation looks at the file's **content** (magic bytes, PDF end marker, DOCX structure), never at the
client's `Content-Type`. The client filename is sanitised and is used for display only; stored files are
named by document id.

### `GET /projects/{p}/documents`  *(implemented — US-03)*

Lists the project's documents, newest first. Query: `status` (filter), `limit` (1–100, default 20), `offset`.
Response: `{ "items": [<document>], "total", "limit", "offset" }`, where `<document>` has the same fields as
the upload response. Needs `view`.

### `GET /documents/{id}`  *(implemented — US-03)*

Returns one document. Poll this for status: `queued` → `processing` (`progress_percent` 10) → `done` (100)
or `failed`. A failed document carries a readable `error_message` prefixed with the stage that failed:
`[storage]`, `[extraction]` or `[persistence]`. A document in a workspace the caller does not belong to is a
**404**, not a 403. Needs `view`.

### `GET /projects/{p}/requirements`  *(implemented — US-04)*

Lists the project's requirements; within a document in source order. Query: `q` (case-insensitive search over
text and printed ID, max 200 chars), `state` (Proposed, Under_Review, Approved, Rejected, Implemented,
Deprecated), `origin` (document, post, change_request), `owner` (user id), `document_id`, `limit` (1–200,
default 50), `offset`. Response: `{ "items": [...], "total", "limit", "offset" }`, each item:

```
{ "requirement_id", "project_id", "document_id",
  "source_req_id" /* null when the document printed none */,
  "body" /* verbatim */, "location", "order_index", "stakeholder_group", "is_protected", "current_version",
  "state", "origin", "owner_id" /* null = unassigned */, "owner_name" }
```

An empty list is a normal response: check the document's `status` / `error_message` to explain it. The "issue
badges" of the US-04 card arrive with the issues tables (Sprint 4).

### `GET /documents/{id}/findings`

Returns classified findings with confidence and rationale (FR-13, FR-14).

```
Response 200:
{
  "findings": [
    {
      "id": "uuid",
      "category": "Conflicting",
      "confidence": 0.87,
      "rationale": "REQ-014 requires X within 2s; REQ-041 requires X within 10s.",
      "requirement_ids": ["REQ-014", "REQ-041"],
      "status": "flagged"
    }
  ]
}
```

### `PATCH /findings/{id}`

Human review action on a flagged finding (FR-18). The original AI output is retained, never overwritten (FR-20).

```
Request:
{ "action": "dismiss" | "confirm" | "merge" | "reclassify",
  "reclassify_to": "Duplicate"   // only if action = reclassify
}
Response 200: updated finding, with original_ai_output preserved
Response 403: finding involves a protected requirement and the caller lacks
              `protected.signoff` (DR-05)
```

## 3. Deferred (Post-MVP) API Surface

US-20 calls for a documented, versioned, public REST API for third-party consumers with configurable per-consumer rate limits (FR-40). This is explicitly deferred beyond the semester MVP — the 10 endpoints above are for the product's own frontend only, not a public integration surface.

## 4. Error Handling Convention

- All endpoints return a consistent `{ "error": { "code", "message", "request_id" } }` body on failure (`details` is added on 422). `request_id` matches the `X-Request-ID` response header — quote it when reporting a problem.
- LLM classification failures retry up to 3x with exponential backoff (NFR-07) before the finding is marked failed rather than silently dropped.
- Validation errors (Pydantic) return 422 with per-field detail.
