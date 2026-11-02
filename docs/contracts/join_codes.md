# Join codes — contract

| | |
|---|---|
| **Producer** | Madhav (`app/services/join_codes.py`, `app/api/join_codes.py`, migration `0005_collaboration`) |
| **Consumers** | Parth (`POST /auth/signup`) · Abhijeet (Join codes tab, join page) · Pranshu (sign-up with code) · Affan (security tests) |
| **Stories** | US-25 (FR-44, FR-77, NFR-35); sign-up side is US-19 (`docs/contracts/permissions.md` §3) |
| **Status** | Sprint 1. Replaces the Sprint 0 draft on `feat/madhav-sprint1-join-codes`, which predated the tenancy model (`memberships`, `roles`) |

## 1. The code

* 8 characters from `23456789ABCDEFGHJKLMNPQRSTUVWXYZ` (digits 2–9 and letters without I and O — 32 symbols), so
  `32^8 = 2^40`: exactly the 40-bit minimum of NFR-35. Generated with `secrets`.
* Shown as `XXXX-XXXX`. Input is canonicalised: trimmed, spaces and hyphens removed, upper-cased. Anything that is not
  8 alphabet characters is treated like an unknown code.
* Stored as `HMAC-SHA256(JOIN_CODE_PEPPER, canonical)` (hex) — never the code. `code_hint` keeps the last four
  characters so managers can tell codes apart (`…4XPA`). The hint is never written to the audit log.
* `JOIN_CODE_PEPPER` must be ≥ 32 characters and not `dev-only-…` in staging/production (the app refuses to start).
  Rotating it invalidates every code.

## 2. Lifecycle

| Field | Meaning |
|---|---|
| `role_id` | role given on joining — a default role or one of the workspace's custom roles; **never** one holding `workspace.manage` or `roles.manage` (Owner, Admin) |
| `project_id` | optional: joining also adds the person to this project's team |
| `expires_at` | creation + 1, 7 or 30 days |
| `max_uses` / `uses` | `NULL` = unlimited; the use that reaches `max_uses` sets `exhausted` |
| `requires_approval` | redemption creates a `join_request` instead of a membership |
| `status` | `active → revoked` (manager) · `active → expired` (time) · `active → exhausted` (uses) |

An active code past `expires_at` is reported and enforced as `expired` immediately; the beat task
`join_codes.expire` (every 15 minutes) writes it down, and expires join requests left `pending` for 14 days.

## 3. Redemption — `redeem(db, code, user) -> Membership | JoinRequest`

1. Canonicalise and hash; `SELECT … FOR UPDATE` the code row (concurrent redemptions serialise on it).
2. Unknown, malformed, expired, used-up or revoked → **`InvalidJoinCodeError`**, one message for all.
3. Already a member and the code is workspace-wide → `ConflictError` (409). A project code for an existing member adds
   them to the project team; if they are already on that team → 409 (no use is spent). A pending request for the same
   workspace → 409, also when two redemptions race for it.
4. `uses += 1` (and `exhausted` if it was the last).
5. With approval: insert a `join_request` (pending, the code's role). Without: `membership.add_member(...,
   via_join_code=True, commit=False)` and, for a project code, `add_project_member(..., via_join_code=True,
   commit=False)`.
6. Audit (`join_code_redeemed` / `join_request_created`) with ids only.

`redeem` **flushes and never commits**: sign-up has already flushed the new user in the same session and rolls the
whole transaction back on any refusal, so a bad code never leaves an account behind.

## 4. Endpoints

| Method and path | Permission | Notes |
|---|---|---|
| `POST /workspaces/{w}/join-codes` | `joincode.manage` (and in the project, for a project code) | body `{role_id, project_id?, expires_in_days: 1\|7\|30, max_uses?, requires_approval}`; 201 with `code` — the only time it is returned; 409 for a privileged role |
| `GET /workspaces/{w}/join-codes` | `joincode.manage` | hint, role, uses, expiry, effective status |
| `DELETE /join-codes/{id}` | `joincode.manage` | 204; idempotent |
| `POST /join` | any signed-in user | body `{code}`; 200 `joined` or 202 `pending_approval`; 400 `invalid_join_code`; 429 after 10 attempts per 10 minutes per address and per user |
| `GET /workspaces/{w}/join-requests?status=` | `members.manage` | pending by default; includes the person's name and e-mail |
| `GET /workspaces/{w}/join-requests/{id}/decision` | `members.manage` | the request and its decision |
| `POST /workspaces/{w}/join-requests/{id}/decision` | `members.manage` | `{approve, role_id?}`; approving may pick another role (still never Owner/Admin); 409 if already decided, past its 14 days, or `role_id` is given for someone already in the workspace (their role is never changed). Concurrent decisions are serialised on the request row |

A code or request of another workspace is a 404, like every other resource (ADR-12).
