# API Documentation

**Planned FastAPI Endpoints**

| | |
|---|---|
| **Base path** | `/api/v1` |
| **Auth** | Bearer JWT (FR-37) on every endpoint except `/auth/login` |
| **Status** | Implemented: `POST /auth/login`, `GET /auth/me`, `POST /documents`, `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/requirements` (Sprint 0–1). Everything else is planned. |

---

## 1. Endpoint Summary (10)

| # | Method & Path | Purpose | FR trace |
|---|---|---|---|
| 1 | `POST /auth/login` | Authenticate, issue JWT | FR-37 |
| 2 | `POST /documents` | Upload an SRS document | FR-01, FR-02 |
| 3 | `GET /documents/{id}` | Get document status/progress | US-03 |
| 4 | `GET /documents/{id}/requirements` | List extracted requirements | FR-04, US-04 |
| 5 | `PATCH /requirements/{id}` | Correct extraction/segmentation, or edit text (triggers impact analysis) | FR-06, FR-24 |
| 6 | `GET /documents/{id}/findings` | List classified findings for a document | FR-27, FR-28 |
| 7 | `PATCH /findings/{id}` | Confirm / dismiss / merge / reclassify a finding | FR-18, FR-20 |
| 8 | `GET /findings/{id}/clarification` | Get or generate the clarification question | FR-22, FR-23 |
| 9 | `GET /requirements/{id}/impact` | Get change-impact analysis for a requirement | FR-24, FR-25 |
| 10 | `GET /workspaces/{id}/dashboard` | Aggregated counts + graph data | FR-27, FR-29 |

## 2. Selected Endpoint Detail

### `POST /documents`  *(implemented, Sprint 1 — US-01)*

Uploads an SRS document and enqueues extraction (FR-01, FR-02). Needs role `analyst` or `admin`.

```
Request:  multipart/form-data { file }       (PDF .pdf or Word .docx; max MAX_UPLOAD_SIZE_MB, default 25)
Response 202  + Location: /api/v1/documents/{document_id}
{
  "document_id": "uuid",
  "status": "queued",                        // queued | processing | done | failed
  "filename": "srs_v3.docx",
  "format": "docx",
  "size_bytes": 36686,
  "progress_percent": 0,
  "error_message": null,
  "requirement_count": 0,
  "uploaded_by": "uuid",
  "uploaded_at": "2026-10-01T04:40:38Z",
  "duplicate_of": null                       // id of an earlier identical upload in this workspace, else null
}
```

`duplicate_of` is informational: a re-upload is still accepted and processed.

**Errors** (body `{"error": {"code", "message", "request_id"}}` — `message` is written to be shown to the user):

| Status | `code` | When |
|---|---|---|
| 400 | `unsupported_file_type` | extension is not `.pdf` / `.docx` (legacy `.doc`, `.txt`, ReqIF get a specific hint) |
| 400 | `empty_file` | zero bytes |
| 400 | `corrupted_file` | content is not the claimed format, or a PDF/DOCX is truncated/unreadable |
| 400 | `file_content_mismatch` | e.g. a Word file renamed `.pdf`, or a password-protected Office file |
| 400 | `unsafe_file` | a `.docx` that expands to an unreasonable size (zip bomb) |
| 403 | `forbidden` | role may not upload (`read_only`, `compliance_reviewer`, `service`) |
| 413 | `payload_too_large` | larger than the limit — refused **before** the body is read when the client declares its size, and cut off mid-stream when it doesn't |
| 422 | `validation_error` | no `file` part in the request |
| 503 | `queue_unavailable` | the job queue is down; nothing was stored — retry |

Validation looks at the file's **content** (magic bytes, PDF end marker, DOCX structure), never at the
client's `Content-Type`. The client filename is sanitised and is used for display only; stored files are
named by document id.

### `GET /documents`  *(implemented, Sprint 1)*

Lists the caller's workspace documents, newest first. Query: `status` (filter), `limit` (1–100, default 20),
`offset`. Response: `{ "items": [<document>], "total", "limit", "offset" }`, where `<document>` has the same
fields as the upload response. Roles: `analyst`, `admin`, `compliance_reviewer`.

### `GET /documents/{id}`  *(implemented, Sprint 1 — US-03)*

Returns one document. Poll this for status: `queued` → `processing` (`progress_percent` 10) → `done` (100)
or `failed`. A failed document carries a readable `error_message` prefixed with the stage that failed:
`[storage]`, `[extraction]` or `[persistence]`. A document in another workspace is a **404**, not a 403.

### `GET /documents/{id}/requirements`  *(implemented, Sprint 1 — US-04)*

Lists extracted requirements in source order. Query: `q` (case-insensitive search over text and ID, max 200
chars), `limit` (1–200, default 50), `offset`. Response: `{ "items": [...], "total", "limit", "offset" }`,
each item:

```
{ "requirement_id", "document_id", "source_req_id" /* null when the document printed none */,
  "body" /* verbatim */, "location", "order_index", "stakeholder_group", "is_protected", "current_version" }
```

An empty list is a normal response: check the document's `status` / `error_message` to explain it.

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
Response 403: finding involves a protected requirement and requires
              the Compliance Reviewer role (DR-05)
```

## 3. Deferred (Post-MVP) API Surface

US-20 calls for a documented, versioned, public REST API for third-party consumers with configurable per-consumer rate limits (FR-40). This is explicitly deferred beyond the semester MVP — the 10 endpoints above are for the product's own frontend only, not a public integration surface.

## 4. Error Handling Convention

- All endpoints return a consistent `{ "error": { "code", "message", "request_id" } }` body on failure (`details` is added on 422). `request_id` matches the `X-Request-ID` response header — quote it when reporting a problem.
- LLM classification failures retry up to 3x with exponential backoff (NFR-07) before the finding is marked failed rather than silently dropped.
- Validation errors (Pydantic) return 422 with per-field detail.
