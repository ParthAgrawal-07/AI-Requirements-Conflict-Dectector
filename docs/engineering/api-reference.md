# API Documentation

**Planned FastAPI Endpoints**

| | |
|---|---|
| **Base path** | `/api/v1` |
| **Auth** | Bearer JWT (FR-37) on every endpoint except `/auth/login` |
| **Status** | Planned — no backend implementation exists yet |

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

- All endpoints return a consistent `{ "error": { "code", "message" } }` body on failure.
- LLM classification failures retry up to 3x with exponential backoff (NFR-07) before the finding is marked failed rather than silently dropped.
- Validation errors (Pydantic) return 422 with per-field detail.
