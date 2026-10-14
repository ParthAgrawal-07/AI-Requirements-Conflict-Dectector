# API Documentation

**FastAPI Endpoints — Live and Planned**

| | |
|---|---|
| **Base path** | `/api/v1` |
| **Auth** | Bearer JWT (FR-37) on every endpoint except `/auth/login` and the health probes |
| **Status** | Auth and health endpoints are live. Everything else is planned. The routers are mounted (behind auth) but have no routes yet |
| **Live docs** | Swagger UI at `http://localhost:8000/docs` is generated from the code and is always current |

---

## 1. Live Endpoints

| Method & Path | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Liveness probe. Always `{"status": "ok"}` |
| `GET /health/ready` | none | Readiness: checks Postgres and Redis. 200 `{"status": "ready", "checks": {...}}` or 503 `"degraded"` |
| `POST /api/v1/auth/login` | none | OAuth2 password form (`username` = email, `password`). Returns `{access_token, token_type: "bearer", expires_in}`. 401 `invalid_credentials` |
| `GET /api/v1/auth/me` | Bearer | The current user: `id, email, full_name, role, workspace_id, is_active, created_at` |

There is no sign-up endpoint by design. Accounts are created with `make seed-demo` or `make create-user`.

## 2. Planned Endpoints

All live under `/api/v1` and require a bearer token. `documents`, `requirements`, `findings` and `reports` routers already enforce this.

| # | Method & Path | Purpose | Trace | Sprint |
|---|---|---|---|---|
| 1 | `POST /documents` | Upload an SRS document | FR-01, FR-02, US-01 | 1 (PR #7) |
| 2 | `GET /documents/{id}` | Document status/progress | US-03 | 1–2 |
| 3 | `GET /documents/{id}/requirements` | List extracted requirements | FR-04, US-04 | 1 |
| 4 | `PATCH /requirements/{id}` | Correct extraction, or edit text (triggers impact analysis) | FR-06, FR-24 | 3 |
| 5 | `GET /documents/{id}/findings` | List findings for a document | FR-27, FR-28 | 2 |
| 6 | `PATCH /findings/{id}` | Confirm / dismiss / merge / reclassify | FR-18, FR-20 | 3 |
| 7 | `GET /findings/{id}/clarification` | Get or generate the clarification question | FR-22, FR-23 | 3 |
| 8 | `GET /requirements/{id}/impact` | Change-impact analysis | FR-24, FR-25 | 3 |
| 9 | `GET /workspaces/{id}/dashboard` | Aggregated counts + graph data | FR-27, FR-29 | 4 |

## 3. Planned Endpoint Detail

### `POST /documents`

Uploads an SRS document and enqueues the analysis pipeline (FR-01, FR-02).

```
Request:  multipart/form-data { file }
Response 202:
{
  "document_id": "uuid",
  "status": "queued",
  "filename": "srs_v3.docx"
}
Response 400: unsupported format or corrupted file
Response 413: file exceeds configured size limit
```

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
      "rationale": "REQ-021 requires a 2s timeout; REQ-023 allows up to 10s.",
      "candidate_pair_id": "uuid",      // pairwise finding...
      "requirement_id": null,           // ...or single-requirement finding (exactly one is set)
      "requirement_ids": ["REQ-021", "REQ-023"],  // source IDs, for display
      "status": "flagged",
      "severity": "high"
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

## 4. Deferred (Post-MVP) API Surface

US-20 calls for a documented, versioned, public REST API for third-party consumers with configurable per-consumer rate limits (FR-40). This is explicitly deferred beyond the semester MVP — the endpoints above are for the product's own frontend only, not a public integration surface.

## 5. Error Handling Convention (implemented)

Every error, including 404s and validation errors, uses one shape (`backend/app/core/errors.py`):

```json
{ "error": { "code": "not_authenticated", "message": "Authentication required", "request_id": "3f2a…" } }
```

| Status | `code` | When |
|---|---|---|
| 401 | `not_authenticated` / `invalid_credentials` | Missing/invalid token, or bad login |
| 403 | `forbidden` | Role not allowed (`require_roles`) |
| 404 | `not_found` | Resource missing. Use this for other workspaces' resources too, so their existence isn't revealed |
| 409 | `conflict` | e.g. duplicate email |
| 422 | `validation_error` | Pydantic validation. Per-field detail in `error.details` |
| 500 | `internal_error` | Unhandled exception (logged with the request ID) |

- Every response carries an `X-Request-ID` header. Send one in and it is reused, so a bug report can quote it.
- Planned for the pipeline: LLM classification calls retry up to 3× with exponential backoff (NFR-07) before the finding is marked failed rather than silently dropped.
